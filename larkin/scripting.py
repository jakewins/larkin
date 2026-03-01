from __future__ import annotations

import dataclasses
from typing import NoReturn

import starlark as sl

from larkin.tools import Tool


@dataclasses.dataclass
class ScriptOk:
    prints: list[str]
    final_answer: str | None = None


@dataclasses.dataclass
class ScriptError:
    prints: list[str]
    error: str


class ScriptWorkspace:
    def __init__(self, tools: list[Tool]):
        self.globals = sl.Globals.standard()
        self.mod = sl.Module()

        self.final_answer: str | None = None
        self.prints: list[str] = []

        # Register user-provided tools
        for tool in tools:
            self.mod.add_callable(tool.name, tool)

        # Always-available builtins
        def _print(*args: object) -> None:
            self.prints.append(str(args[0]) if len(args) == 1 else str(args))

        self.mod.add_callable("print", _print)

        def final_answer(answer: str) -> None:
            self.final_answer = answer

        self.mod.add_callable("final_answer", final_answer)

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
