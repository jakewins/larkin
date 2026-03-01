import dataclasses
import enum
import typing as t


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    CODE_EXEC = "code-exec"
    CODE_RESULT = "code-result"

    @classmethod
    def roles(cls) -> list[str]:
        return [r.value for r in cls]


@dataclasses.dataclass
class TextContent:
    text: str
    # Used by model implementations to attach provider-specific metadata that
    # needs to round-trip back through conversation history
    meta: dict[str, t.Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class CodeContent:
    thought: str
    code: str
    # See TextContent
    meta: dict[str, t.Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class CodeSuccess:
    observations: str
    # See TextContent
    meta: dict[str, t.Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class CodeError:
    # Error is expected to contain the observations as well, if any executed before the error
    error: str
    # See TextContent
    meta: dict[str, t.Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ChatMessage:
    role: MessageRole
    content: list[TextContent | CodeContent | CodeSuccess | CodeError]


class Model(t.Protocol):
    def generate(
        self, messages: list[ChatMessage], with_code_tool: bool = True
    ) -> ChatMessage: ...
