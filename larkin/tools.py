from __future__ import annotations

import dataclasses
import enum
import inspect
import typing as t


# ---------------------------------------------------------------------------
# Opaque value type
# ---------------------------------------------------------------------------


class OpaqueValue:
    """A value that is opaque to the LLM agent — it can be passed between tools
    but never inspected, printed, or used as a string.

    Tools that return OpaqueValue produce handles the agent can store and forward
    to other opaque-aware tools, but the agent's Starlark code cannot read the
    contents.  Tools that accept OpaqueValue parameters declare so via their type
    annotations; the ScriptWorkspace enforces that opaque values only reach those
    parameters.
    """

    __slots__ = ("_value",)

    def __init__(self, value: object):
        self._value = value

    @property
    def value(self) -> object:
        return self._value

    def __str__(self) -> str:
        return "<opaque value>"

    def __repr__(self) -> str:
        return "OpaqueValue(<redacted>)"


# ---------------------------------------------------------------------------
# Tool protocol and concrete implementation
# ---------------------------------------------------------------------------


class OpaquePolicy(enum.Enum):
    """Declares how a tool parameter interacts with OpaqueValue.

    REJECT: no opaque values allowed anywhere in the argument (recursive check).
    SCALAR: the parameter itself is an OpaqueValue.
    IN_LIST: the parameter is list[OpaqueValue].
    IN_DICT: the parameter is dict[K, OpaqueValue].
    """

    REJECT = "reject"
    SCALAR = "scalar"
    IN_LIST = "in_list"
    IN_DICT = "in_dict"


@dataclasses.dataclass(frozen=True)
class ToolParam:
    name: str
    type: str
    opaque_policy: OpaquePolicy = OpaquePolicy.REJECT


class Tool(t.Protocol):
    """Protocol for tools that can be registered in the scripting sandbox.

    Any object with the right attributes and __call__ satisfies this protocol.
    Use Tool.from_function() or FunctionTool.from_function() to wrap a plain
    Python function.
    """

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> list[ToolParam]: ...

    @property
    def return_type(self) -> str | None: ...

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> t.Any: ...

    @staticmethod
    def from_function(fn: t.Callable[..., t.Any]) -> FunctionTool:
        """Convenience factory: wrap a typed, docstring'd function as a Tool."""
        return FunctionTool.from_function(fn)


def _annotation_str(annotation: t.Any) -> str:
    """Convert a type annotation to a readable string."""
    if annotation is inspect.Parameter.empty:
        return "Any"
    if hasattr(annotation, "__args__"):
        return str(annotation).replace("typing.", "")
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _opaque_policy_from_annotation(annotation: t.Any) -> OpaquePolicy:
    """Derive the OpaquePolicy for a parameter from its type annotation."""
    if annotation is OpaqueValue:
        return OpaquePolicy.SCALAR
    origin = t.get_origin(annotation)
    args = t.get_args(annotation)
    if origin is list and args and args[0] is OpaqueValue:
        return OpaquePolicy.IN_LIST
    if origin is dict and len(args) >= 2 and args[1] is OpaqueValue:
        return OpaquePolicy.IN_DICT
    return OpaquePolicy.REJECT


class FunctionTool:
    """Concrete Tool implementation that wraps a plain Python function."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters: list[ToolParam],
        return_type: str | None,
        fn: t.Callable[..., t.Any],
    ):
        self._name = name
        self._description = description
        self._parameters = parameters
        self._return_type = return_type
        self._fn = fn

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> list[ToolParam]:
        return self._parameters

    @property
    def return_type(self) -> str | None:
        return self._return_type

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> t.Any:
        return self._fn(*args, **kwargs)

    @staticmethod
    def from_function(fn: t.Callable[..., t.Any]) -> FunctionTool:
        """Build a FunctionTool by introspecting a typed, docstring'd function."""
        sig = inspect.signature(fn)
        hints = t.get_type_hints(fn)

        params: list[ToolParam] = []
        for pname, param in sig.parameters.items():
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                raise ValueError(
                    f"from_function does not support *args/**kwargs "
                    f"(found '{pname}' in {getattr(fn, '__name__', '?')}). "
                    f"Declare all parameters explicitly."
                )
            annotation = hints.get(pname, param.annotation)
            params.append(
                ToolParam(
                    name=pname,
                    type=_annotation_str(annotation),
                    opaque_policy=_opaque_policy_from_annotation(annotation),
                )
            )

        ret = hints.get("return", sig.return_annotation)
        return_type = None if ret is inspect.Parameter.empty else _annotation_str(ret)

        name = getattr(fn, "__name__", None)
        if name is None:
            raise ValueError("from_function requires a function with __name__")

        return FunctionTool(
            name=name,
            description=inspect.getdoc(fn) or "",
            parameters=params,
            return_type=return_type,
            fn=fn,
        )

    def __repr__(self) -> str:
        return f"FunctionTool({self._name!r})"


# ---------------------------------------------------------------------------
# Doc generation
# ---------------------------------------------------------------------------


def generate_tool_docs(tools: list[Tool]) -> str:
    """Generate Starlark-style documentation for a list of Tools."""
    parts: list[str] = []
    for tool in tools:
        param_str = ", ".join(f"{p.name}: {p.type}" for p in tool.parameters)
        ret = f" -> {tool.return_type}" if tool.return_type else ""
        signature = f"def {tool.name}({param_str}){ret}:"

        doc_lines = tool.description.strip().splitlines()
        indented_doc = "\n".join(
            f"    {line}" if line.strip() else "" for line in doc_lines
        )
        parts.append(f"{signature}\n    '''\n{indented_doc}\n    '''")

    return "\n\n".join(parts)
