from __future__ import annotations
import dataclasses
from larkin import models
import typing as t


@dataclasses.dataclass
class SystemPromptStep:
    system_prompt: str

    def to_messages(self) -> list[models.ChatMessage]:
        return [
            models.ChatMessage(
                role=models.MessageRole.SYSTEM,
                content=[models.TextContent(self.system_prompt)],
            )
        ]


@dataclasses.dataclass
class TaskStep:
    task: str

    def to_messages(self) -> list[models.ChatMessage]:
        content = [models.TextContent(f"New task:\n{self.task}")]
        return [models.ChatMessage(role=models.MessageRole.USER, content=content)]


@dataclasses.dataclass
class ActionStep:
    thought: str
    code_action: str
    output: str
    outcome: t.Literal["unknown", "ok", "failed", "deadline_exceeded"]
    error: str | None = None
    final_answer: str | None = None
    # Metadata for various things, used to track the 'thought_signature' google attaches to their
    # responses for instance, which is required to be returned when cycling back to the LLM
    meta: dict[str, t.Any] = dataclasses.field(default_factory=dict)

    @staticmethod
    def from_error(error: str) -> ActionStep:
        return ActionStep(
            thought="",
            code_action="",
            output="",
            outcome="failed",
            error=error,
            final_answer=None,
        )

    def to_messages(self) -> list[models.ChatMessage]:
        messages = []
        messages.append(
            models.ChatMessage(
                role=models.MessageRole.ASSISTANT,
                content=[
                    models.CodeContent(
                        thought=self.thought.strip(),
                        code=self.code_action,
                        meta=self.meta,
                    )
                ],
            )
        )

        if not self.error:
            messages.append(
                models.ChatMessage(
                    role=models.MessageRole.CODE_RESULT,
                    content=[
                        models.CodeSuccess(
                            observations=self.output,
                        )
                    ],
                )
            )
        else:
            error_message = (
                "Error:\n"
                + self.error
                + "\nNow let's retry: take care not to repeat previous errors! If you have retried several times, try a completely different approach.\n"
            )

            messages.append(
                models.ChatMessage(
                    role=models.MessageRole.CODE_RESULT,
                    content=[models.CodeError(error=error_message)],
                )
            )
        return messages


Step = SystemPromptStep | TaskStep | ActionStep


class AgentMemory:
    def __init__(self, system_prompt: str):
        self.system_prompt = SystemPromptStep(system_prompt)
        self.steps: list[TaskStep | ActionStep] = []

    def to_messages(self) -> list[models.ChatMessage]:
        out = self.system_prompt.to_messages()
        for step in self.steps:
            out.extend(step.to_messages())
        return out
