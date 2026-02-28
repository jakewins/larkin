from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from larkin import memory

console = Console()

_step_number = 0


def print_action_step(step: memory.ActionStep):
    global _step_number
    _step_number += 1

    success = step.outcome == "ok"
    border_style = "green" if success else "red"
    status_label = "OK" if success else "FAILED"

    # Thought
    parts = []
    if step.thought:
        thought = Text(step.thought.strip(), style="italic")
        thought_heading = Text("Thinking", style="bold")
        parts.append(Text.assemble(thought_heading, "\n", thought))
        parts.append(Text(""))

    # Syntax-highlighted code (starlark ≈ python syntax)
    if step.code_action:
        parts.append(
            Syntax(
                step.code_action.strip(), "python", theme="monokai", line_numbers=True
            )
        )
        parts.append(Text(""))

    # Output, truncated to last 3 lines
    output_text = step.output.replace("\\n", "\n").strip() if step.output else ""
    if output_text:
        lines = output_text.splitlines()
        if len(lines) > 3:
            truncated = f"... ({len(lines) - 3} lines hidden)\n" + "\n".join(lines[-3:])
        else:
            truncated = output_text
        output_heading = Text("Output", style="bold")
        parts.append(Text.assemble(output_heading, "\n", Text(truncated, style="dim")))

    # Error message
    if step.error and not success:
        error_lines = step.error.strip().splitlines()
        if len(error_lines) > 12:
            error_text = f"... ({len(error_lines) - 12} lines hidden)\n" + "\n".join(
                error_lines[-12:]
            )
        else:
            error_text = step.error.strip()
        error_heading = Text("Error", style="bold red")
        parts.append(Text.assemble(error_heading, "\n", Text(error_text, style="red")))

    title = f"Step {_step_number} \u2500 {status_label}"
    panel = Panel(
        Group(*parts),
        title=title,
        border_style=border_style,
        padding=(1, 2),
    )
    console.print(panel)


def print_final_answer(final_answer: str):
    panel = Panel(
        Group(*[Text(final_answer)]),
        title="Final Answer",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(panel)
