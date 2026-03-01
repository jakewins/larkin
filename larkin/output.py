from __future__ import annotations

import logging
import typing as t

from larkin import memory

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text

    _has_rich = True
except ImportError:
    _has_rich = False


class Output(t.Protocol):
    """Observer for agent execution events."""

    def on_step(self, step: memory.ActionStep) -> None: ...
    def on_final_answer(self, answer: str) -> None: ...


class SilentOutput:
    """No side effects. Makes run() behave as a pure function."""

    def on_step(self, step: memory.ActionStep) -> None:
        pass

    def on_final_answer(self, answer: str) -> None:
        pass


class LogOutput:
    """Plain-text structured logging via stdlib logging."""

    def __init__(self, logger: logging.Logger | None = None):
        self._log = logger or logging.getLogger("larkin.agent")
        self._step_number = 0

    def on_step(self, step: memory.ActionStep) -> None:
        self._step_number += 1
        status = "OK" if step.outcome == "ok" else "FAILED"
        self._log.info("Step %d — %s", self._step_number, status)
        if step.thought:
            self._log.info("Thought: %s", step.thought.strip())
        if step.code_action:
            self._log.info("Code:\n%s", step.code_action.strip())
        if step.output:
            self._log.info("Output: %s", step.output.strip())
        if step.error and step.outcome != "ok":
            self._log.warning("Error: %s", step.error.strip())

    def on_final_answer(self, answer: str) -> None:
        self._log.info("Final answer: %s", answer)


class RichOutput:
    """Interactive terminal output with Rich panels."""

    def __init__(self) -> None:
        if not _has_rich:
            raise ImportError(
                "RichOutput requires the 'rich' package. "
                "Install it with: pip install larkin[extras]"
            )
        self._console = Console()
        self._step_number = 0

    def on_step(self, step: memory.ActionStep) -> None:
        self._step_number += 1

        success = step.outcome == "ok"
        border_style = "green" if success else "red"
        status_label = "OK" if success else "FAILED"

        parts: list[Text | Syntax] = []
        if step.thought:
            thought = Text(step.thought.strip(), style="italic")
            thought_heading = Text("Thinking", style="bold")
            parts.append(Text.assemble(thought_heading, "\n", thought))
            parts.append(Text(""))

        # Syntax-highlighted code (starlark ≈ python syntax)
        if step.code_action:
            parts.append(
                Syntax(
                    step.code_action.strip(),
                    "python",
                    theme="monokai",
                    line_numbers=True,
                )
            )
            parts.append(Text(""))

        # Output, truncated to last 3 lines
        output_text = step.output.replace("\\n", "\n").strip() if step.output else ""
        if output_text:
            lines = output_text.splitlines()
            if len(lines) > 3:
                truncated = f"... ({len(lines) - 3} lines hidden)\n" + "\n".join(
                    lines[-3:]
                )
            else:
                truncated = output_text
            output_heading = Text("Output", style="bold")
            parts.append(
                Text.assemble(output_heading, "\n", Text(truncated, style="dim"))
            )

        # Error message
        if step.error and not success:
            error_lines = step.error.strip().splitlines()
            if len(error_lines) > 12:
                error_text = (
                    f"... ({len(error_lines) - 12} lines hidden)\n"
                    + "\n".join(error_lines[-12:])
                )
            else:
                error_text = step.error.strip()
            error_heading = Text("Error", style="bold red")
            parts.append(
                Text.assemble(error_heading, "\n", Text(error_text, style="red"))
            )

        title = f"Step {self._step_number} \u2500 {status_label}"
        panel = Panel(
            Group(*parts),
            title=title,
            border_style=border_style,
            padding=(1, 2),
        )
        self._console.print(panel)

    def on_final_answer(self, answer: str) -> None:
        panel = Panel(
            Group(*[Text(answer)]),
            title="Final Answer",
            border_style="blue",
            padding=(1, 2),
        )
        self._console.print(panel)
