import json
import os

import pytest

from larkin.models import CodeContent, CodeError, CodeSuccess, TextContent
from larkin.models.google import GoogleModel


@pytest.mark.parametrize(
    "content,check",
    [
        (
            CodeContent(thought="t", code="c", meta={}),
            lambda p: json.loads(p.text) == {"thought": "t", "code": "c"},
        ),
        (
            CodeSuccess(observations="42"),
            lambda p: p.text == "Observation: 42",
        ),
        (
            CodeError(error="boom"),
            lambda p: p.text == "Error: boom",
        ),
        (
            TextContent("hello"),
            lambda p: p.text == "hello",
        ),
    ],
    ids=["code_content", "code_success", "code_error", "text_content"],
)
def test_part_from_content(content, check):
    part = GoogleModel._part_from_content(content)
    assert check(part)
    assert part.function_call is None
    assert part.function_response is None


@pytest.mark.skipif(
    "GOOGLE_API_KEY" not in os.environ,
    reason="requires GOOGLE_API_KEY",
)
def test_integration_happy_path():
    from larkin.agents import Agent

    agent = Agent(model=GoogleModel("gemini-2.5-flash"))
    result = agent.run("What is 2 + 2?")
    assert "4" in result
