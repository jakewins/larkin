"""
Property-based test suite that tries to find ways to leak opaque strings,
using Hypothesis.

We give Hypothesis a way to generate tool signatures and valid Starlark code.
Its job is to try and come up with a combination of Starlark code and tool type
signature that gets past Larkin's runtime checks and lets an opaque value leak
into any output.

The approach: identifiers are drawn from a small fixed pool, so interesting
patterns (variable hops, shadowing, dead references) emerge.
"""

from __future__ import annotations

from dataclasses import dataclass

import hypothesis.strategies as st
from hypothesis import given, settings

from larkin.scripting import ScriptError, ScriptOk, ScriptWorkspace
from larkin.tools import FunctionTool, OpaquePolicy, OpaqueValue, ToolParam

# Hypothesis' goal is to smuggle out this value
SECRET_SENTINEL = "TOP SECRET DATA"


def _get_secret() -> OpaqueValue:
    """Return an opaque handle wrapping secret data."""
    return OpaqueValue(SECRET_SENTINEL)


_GET_SECRET = FunctionTool.from_function(_get_secret)


def _assert_no_leak(result: ScriptOk | ScriptError) -> None:
    """The sentinel must never appear anywhere in the output."""
    assert SECRET_SENTINEL not in str(result)


def _make_target_tool(params: list[ToolParam]) -> FunctionTool:
    """Build a target tool that echoes its arguments.

    Constructed directly since from_function rejects *args. The validation
    wrapper checks tool.parameters, not the underlying function signature.

    At REJECT positions the fn naively extracts .value — modelling a tool that
    doesn't know about opaque handles. The REJECT check is what prevents
    OpaqueValues from ever reaching this code; if it's bypassed, the secret
    leaks into the return value. At SCALAR/IN_LIST/IN_DICT positions the fn
    uses str(), modelling an opaque-aware tool that handles values safely.
    """

    def _echo(*args: object) -> str:
        parts: list[str] = []
        for i, a in enumerate(args):
            if (
                i < len(params)
                and params[i].opaque_policy == OpaquePolicy.REJECT
                and isinstance(a, OpaqueValue)
            ):
                parts.append(str(a.value))
            else:
                parts.append(str(a))
        return " ".join(parts)

    return FunctionTool(
        name="target",
        description="Target tool for property testing",
        parameters=params,
        return_type="str",
        fn=_echo,
    )


# We describe to hypothesis how to write starlark by giving it these AST-like data structures,
# which we then render to valid Starlark. This does mean we're not testing invalid starlark, but
# we expect that security boundary to be upheld by starlark itself.


@dataclass
class Var:
    name: str


@dataclass
class Literal:
    """Raw Starlark text, e.g. '"hello"', '42', 'True'."""

    code: str


@dataclass
class ListExpr:
    elements: list[Expr]


@dataclass
class DictExpr:
    entries: list[tuple[str, Expr]]


@dataclass
class Call:
    fn: str
    args: list[Expr]


@dataclass
class Index:
    obj: Expr
    key: Expr


type Expr = Var | Literal | ListExpr | DictExpr | Call | Index


@dataclass
class Assign:
    target: str
    value: Expr


@dataclass
class ExprStmt:
    expr: Expr


@dataclass
class ForStmt:
    var: str
    iterable: Expr
    body: list[Stmt]


@dataclass
class IfStmt:
    condition: Literal
    then_body: list[Stmt]
    else_body: list[Stmt]


type Stmt = Assign | ExprStmt | ForStmt | IfStmt


def _render_expr(expr: Expr) -> str:
    match expr:
        case Var(name=name):
            return name
        case Literal(code=code):
            return code
        case ListExpr(elements=elements):
            return "[" + ", ".join(_render_expr(e) for e in elements) + "]"
        case DictExpr(entries=entries):
            parts = (f'"{k}": {_render_expr(v)}' for k, v in entries)
            return "{" + ", ".join(parts) + "}"
        case Call(fn=fn, args=args):
            return fn + "(" + ", ".join(_render_expr(a) for a in args) + ")"
        case Index(obj=obj, key=key):
            return _render_expr(obj) + "[" + _render_expr(key) + "]"


def _render_stmt(stmt: Stmt, indent: int = 0) -> str:
    prefix = "    " * indent
    match stmt:
        case Assign(target=target, value=value):
            return f"{prefix}{target} = {_render_expr(value)}"
        case ExprStmt(expr=expr):
            return f"{prefix}{_render_expr(expr)}"
        case ForStmt(var=var, iterable=iterable, body=body):
            lines = [f"{prefix}for {var} in {_render_expr(iterable)}:"]
            lines.extend(_render_stmt(s, indent + 1) for s in body)
            return "\n".join(lines)
        case IfStmt(condition=cond, then_body=then_body, else_body=else_body):
            lines = [f"{prefix}if {_render_expr(cond)}:"]
            lines.extend(_render_stmt(s, indent + 1) for s in then_body)
            if else_body:
                lines.append(f"{prefix}else:")
                lines.extend(_render_stmt(s, indent + 1) for s in else_body)
            return "\n".join(lines)


def render(stmts: list[Stmt]) -> str:
    """Render a list of Starlark AST nodes to a script string."""
    return "\n".join(_render_stmt(s) for s in stmts)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

IDENTS = ["x", "v1", "v2", "v3", _GET_SECRET.name]


def st_ident():
    return st.sampled_from(IDENTS)


def st_expr():
    return st.recursive(
        st.one_of(
            st_ident().map(Var),
            st.sampled_from([Literal('"safe"'), Literal("42")]),
        ),
        lambda inner: st.one_of(
            inner.map(lambda e: ListExpr([e])),
            inner.map(lambda e: DictExpr([("k", e)])),
            inner.map(lambda e: Index(ListExpr([e]), Literal("0"))),
        ),
        max_leaves=5,
    )


def st_print_stmt():
    """Generate a print(<expr>) statement."""
    return st_expr().map(lambda e: ExprStmt(Call("print", [e])))


@st.composite
def st_stmts(draw, inner: list[Stmt]) -> list[Stmt]:
    prints_before = [draw(st_print_stmt()) for _ in range(draw(st.integers(0, 1)))]
    prints_after = [draw(st_print_stmt()) for _ in range(draw(st.integers(0, 1)))]
    stmts = prints_before + inner + prints_after

    n = draw(st.integers(0, 3))
    for _ in range(n):
        kind = draw(st.sampled_from(["assign", "for", "if_true", "if_false"]))
        match kind:
            case "assign":
                stmts = [Assign(draw(st_ident()), draw(st_expr()))] + stmts
            case "for":
                stmts = [ForStmt(draw(st_ident()), draw(st_expr()), stmts)]
            case "if_true":
                stmts = [IfStmt(Literal("True"), stmts, [])]
            case "if_false":
                stmts = [IfStmt(Literal("False"), [ExprStmt(Literal("0"))], stmts)]
    return stmts


@st.composite
def st_tool_params(draw) -> list[ToolParam]:
    """Generate 1-3 tool params with at least one REJECT."""
    n = draw(st.integers(min_value=1, max_value=3))
    policies = draw(
        st.lists(
            st.sampled_from(
                [
                    OpaquePolicy.REJECT,
                    OpaquePolicy.SCALAR,
                    OpaquePolicy.IN_DICT,
                    OpaquePolicy.IN_LIST,
                ]
            ),
            min_size=n,
            max_size=n,
        ).filter(lambda ps: OpaquePolicy.REJECT in ps)
    )
    return [
        ToolParam(name=f"p{i}", type="str", opaque_policy=p)
        for i, p in enumerate(policies)
    ]


@st.composite
def st_script(draw, params: list[ToolParam]) -> list[Stmt]:
    # x is set to the secret value
    preamble = [Assign("x", Call(_GET_SECRET.name, []))]
    call_args = [draw(st_expr()) for _ in range(len(params))]
    # Sometimes capture the result and print it — this surfaces leaks
    # through the target tool's return value into the script output.
    if draw(st.booleans()):
        attack: list[Stmt] = [
            Assign("_result", Call("target", call_args)),
            ExprStmt(Call("print", [Var("_result")])),
        ]
    else:
        attack = [ExprStmt(Call("target", call_args))]
    body = draw(st_stmts(attack))  # type: ignore[missing-argument]  # hypothesis ParamSpec
    return preamble + body


@given(data=st.data())
@settings(max_examples=500)
def test_sentinel_never_leaks(data) -> None:
    """Opaque values are blocked even through control flow and rebinding."""
    # Generate a tool with mixed Opaque / normal args
    params = data.draw(st_tool_params())  # type: ignore[missing-argument]  # hypothesis ParamSpec
    tool = _make_target_tool(params)

    # Generate a script that uses the tool in lots of ways
    stmts = data.draw(st_script(params))  # type: ignore[missing-argument]  # hypothesis ParamSpec
    script = render(stmts)

    ws = ScriptWorkspace([_GET_SECRET, tool])
    result = ws.eval(script)
    _assert_no_leak(result)
