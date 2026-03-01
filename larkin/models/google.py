import json
import time

import google.genai
import google.genai.errors
import google.genai.types

from larkin.models import (
    ChatMessage,
    CodeContent,
    CodeError,
    CodeSuccess,
    MessageRole,
    Model,
    TextContent,
)

STARLARK_RESPONSE_SCHEMA = google.genai.types.Schema(
    type=google.genai.types.Type.OBJECT,
    properties={
        "thought": google.genai.types.Schema(type=google.genai.types.Type.STRING),
        "code": google.genai.types.Schema(type=google.genai.types.Type.STRING),
    },
    required=["thought", "code"],
)


class GoogleModel(Model):
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.client = google.genai.Client()
        self.model = model

    def generate(
        self, messages: list[ChatMessage], with_code_tool: bool = True
    ) -> ChatMessage:
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

        if with_code_tool:
            config = google.genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=STARLARK_RESPONSE_SCHEMA,
            )
        else:
            config = google.genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
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
                # TODO actual handling
                print("llm server error, sleeping")
                time.sleep(30)

        if not response.parts:
            assert response.candidates is not None
            raise ValueError(
                f"LLM returned no reply: {response.candidates[0].finish_reason}"
            )

        if with_code_tool:
            assert response.text is not None
            parsed = json.loads(response.text)
            return ChatMessage(
                MessageRole.CODE_EXEC,
                [
                    CodeContent(
                        thought=parsed.get("thought", ""),
                        code=parsed["code"],
                        meta={
                            "google.thought_signature": response.parts[
                                -1
                            ].thought_signature,
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
                    text=text,
                    thought_signature=meta.get("google.thought_signature"),
                )
            case CodeContent(thought=thought, code=code, meta=meta):
                return google.genai.types.Part(
                    text=json.dumps({"thought": thought, "code": code}),
                    thought_signature=meta.get("google.thought_signature"),
                )
            case CodeSuccess(observations=observations):
                return google.genai.types.Part(
                    text=f"Observation: {observations}",
                )
            case CodeError(error=error):
                return google.genai.types.Part(
                    text=f"Error: {error}",
                )
            case other:
                raise ValueError(other)
