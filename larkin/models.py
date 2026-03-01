import enum
import dataclasses
import typing as t
import time
from google import genai
import google.genai.types
import google.genai.errors


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    CODE_EXEC = "code-exec"
    CODE_RESULT = "code-result"

    @classmethod
    def roles(cls):
        return [r.value for r in cls]


@dataclasses.dataclass
class TextContent:
    text: str
    # Used by things like the google model to attach "thought" metadata that needs to be returned for history to work
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
        self, messages: list[ChatMessage], with_code_tool=True
    ) -> ChatMessage: ...


STARLARK_TOOL_SCHEMA = google.genai.types.FunctionDeclaration(
    name="exec_starlark",
    description="Executes the provided starlark script, and associates the execution with the provided thought process",
    parameters=google.genai.types.Schema(
        type=google.genai.types.Type.OBJECT,
        properties={
            "thought": google.genai.types.Schema(
                type=google.genai.types.Type.STRING,
                description="Thought process behind this code. What are we trying to achieve, how will the code achieve it?",
            ),
            "code": google.genai.types.Schema(
                type=google.genai.types.Type.STRING,
                description="Starlark script, the script can call the functions outlined in the system prompt",
            ),
        },
        required=["thought", "code"],
    ),
)


class GoogleModel(Model):
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.client = genai.Client()
        self.model = model

    def generate(self, messages: list[ChatMessage], with_code_tool=True) -> ChatMessage:
        # If there's a system prompt, provide that in the dedicated argument, this
        # supposedly hardens it against injection (LOL ok bro) and improves caching
        match messages[0]:
            case ChatMessage(role=MessageRole.SYSTEM, content=content):
                system_instruction = [
                    GoogleModel._part_from_content(c) for c in content
                ]
                messages = messages[1:]
            case _:
                system_instruction = None

        tools = []
        if with_code_tool:
            tools.append(
                google.genai.types.Tool(function_declarations=[STARLARK_TOOL_SCHEMA])
            )

        config = google.genai.types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
        )

        while True:
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[self._content_from_message(m) for m in messages],
                    config=config,
                )
                break
            except google.genai.errors.ServerError:
                print("llm server error, sleeping")
                time.sleep(30)

        if not response.parts:
            assert response.candidates is not None
            raise ValueError(
                f"LLM returned no reply: {response.candidates[0].finish_reason}"
            )

        if with_code_tool:
            for part in response.parts:
                if part.function_call:
                    # The model is prone to calling final_answer as a tool rather than as a starlark code block
                    # paper over that problem
                    assert part.function_call.args is not None
                    if part.function_call.name == "final_answer":
                        text_no_triple_quotes = part.function_call.args.get(
                            "answer", ""
                        ).replace("'''", "")
                        return ChatMessage(
                            MessageRole.CODE_EXEC,
                            [
                                CodeContent(
                                    thought="<< system: model invoked final_answer as tool, remapping to code >>",
                                    code=f"final_answer(answer='''{text_no_triple_quotes}''')",
                                    meta={
                                        "google.function_call_id": part.function_call.id,
                                        "google.thought_signature": part.thought_signature,
                                    },
                                )
                            ],
                        )
                    return ChatMessage(
                        MessageRole.CODE_EXEC,
                        [
                            CodeContent(
                                thought=part.function_call.args.get("thought", ""),
                                code=part.function_call.args["code"],
                                meta={
                                    "google.function_call_id": part.function_call.id,
                                    "google.thought_signature": part.thought_signature,
                                },
                            )
                        ],
                    )

        return ChatMessage(
            MessageRole.ASSISTANT,
            [
                TextContent(
                    text=response.text or "",
                    meta={
                        "google.thought_signature": response.parts[
                            -1
                        ].thought_signature,
                    },
                )
            ],
        )

    @staticmethod
    def _content_from_message(message: ChatMessage) -> google.genai.types.Content:
        """Map from ChatMessage to the Content structure google wants"""
        return google.genai.types.Content(
            role="model"
            if message.role in {MessageRole.ASSISTANT, MessageRole.CODE_EXEC}
            else "user",
            parts=[GoogleModel._part_from_content(c) for c in message.content],
        )

    @staticmethod
    def _part_from_content(
        content: TextContent | CodeContent | CodeSuccess | CodeError,
    ) -> google.genai.types.Part:
        match content:
            case TextContent(text=text, meta=meta):
                return google.genai.types.Part(
                    text=text, thought_signature=meta.get("google.thought_signature")
                )
            case CodeContent(thought=thought, code=code, meta=meta):
                return google.genai.types.Part(
                    function_call=google.genai.types.FunctionCall(
                        name="exec_starlark",
                        id=meta.get("google.function_call_id"),
                        args={
                            "thought": thought,
                            "code": code,
                        },
                    ),
                    thought_signature=meta.get("google.thought_signature"),
                )
            case CodeSuccess(observations=observations, meta=meta):
                return google.genai.types.Part(
                    function_response=google.genai.types.FunctionResponse(
                        name="exec_starlark",
                        id=meta.get("google.function_call_id"),
                        response={
                            "output": observations,
                        },
                    ),
                    thought_signature=meta.get("google.thought_signature"),
                )
            case CodeError(error=error, meta=meta):
                return google.genai.types.Part(
                    function_response=google.genai.types.FunctionResponse(
                        name="exec_starlark",
                        id=meta.get("google.function_call_id"),
                        response={
                            "error": error,
                        },
                    ),
                    thought_signature=meta.get("google.thought_signature"),
                )
            case other:
                raise ValueError(other)
