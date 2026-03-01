from __future__ import annotations

import dataclasses
import typing as t
from typing import NoReturn

import starlark as sl

from larkin.tools import OpaquePolicy, OpaqueValue, Tool, FunctionTool


@dataclasses.dataclass
class ScriptOk:
    prints: list[str]
    final_answer: str | None = None


@dataclasses.dataclass
class ScriptError:
    prints: list[str]
    error: str


def _contains_opaque(value: object) -> bool:
    """Recursively check whether a value contains an OpaqueValue, catching
    attempts to smuggle opaque data inside lists, tuples, or dicts."""
    if isinstance(value, OpaqueValue):
        return True
    if isinstance(value, (list, tuple)):
        return any(_contains_opaque(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_opaque(v) for v in value.values())
    return False


def _make_validated_wrapper(tool: Tool) -> t.Callable[..., t.Any]:
    """Wrap a tool callable so that OpaqueValue arguments are only accepted
    for parameters whose opaque_policy allows it, and OpaqueValue return values
    are auto-wrapped in OpaquePythonObject for Starlark."""

    def wrapper(*args: t.Any, **kwargs: t.Any) -> t.Any:
        for i, arg in enumerate(args):
            if i >= len(tool.parameters):
                break
            param = tool.parameters[i]
            match param.opaque_policy:
                case OpaquePolicy.REJECT:
                    if _contains_opaque(arg):
                        raise ValueError(
                            f"Parameter '{param.name}' of tool '{tool.name}' "
                            f"does not accept opaque values — only tools that "
                            f"explicitly declare OpaqueValue parameters can "
                            f"receive them"
                        )
                case _:
                    pass  # tool declared it handles opaque here
        result = tool(*args, **kwargs)
        if isinstance(result, OpaqueValue):
            return sl.OpaquePythonObject(result)
        return result

    return wrapper


class ScriptWorkspace:
    def __init__(self, tools: list[Tool]):
        self.globals = sl.Globals.standard()
        self.mod = sl.Module()

        self.final_answer: str | None = None
        self.prints: list[str] = []

        # Register user-provided tools with opaque-value validation
        for tool in tools:
            self.mod.add_callable(tool.name, _make_validated_wrapper(tool))

        # Always-available builtins
        def _print(value: object) -> None:
            self.prints.append(str(value))

        self.mod.add_callable(
            "print", _make_validated_wrapper(FunctionTool.from_function(_print))
        )

        def final_answer(answer: object) -> None:
            self.final_answer = str(answer)

        self.mod.add_callable(
            "final_answer",
            _make_validated_wrapper(FunctionTool.from_function(final_answer)),
        )

        def load(name: str) -> NoReturn:
            raise FileNotFoundError("loading is not available")

        self.file_loader = sl.FileLoader(load)

    def eval(self, script: str) -> ScriptOk | ScriptError:
        try:
            dialect = sl.Dialect.extended()
            dialect.enable_top_level_stmt = True
            ast = sl.parse("script.star", script, dialect=dialect)

            # Clear the side-effects of any prior runs, other than variables
            self.prints = []

            sl.eval(self.mod, ast, self.globals, self.file_loader)

            return ScriptOk(self.prints, self.final_answer)
        except sl.StarlarkError as e:
            return ScriptError(prints=self.prints, error=str(e))
        except FileNotFoundError as e:
            return ScriptError(prints=self.prints, error=str(e))
        except ValueError as e:
            return ScriptError(prints=self.prints, error=str(e))
