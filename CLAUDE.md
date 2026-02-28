# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run pytest                        # Run all tests
uv run pytest larkin/scripting_test.py::test_web_search  # Run a single test
uv run ruff check                    # Lint
uv run ruff format                   # Format
uv run ty check                      # Type check
```

## Architecture

Larkin is an agentic AI framework. An LLM generates Starlark code to accomplish tasks, which is executed in a sandboxed environment with tool functions available.

**Agentic loop** (`agents.py`): `Agent.run()` drives the core loop — send conversation history to LLM, execute returned Starlark code, observe results, repeat until `final_answer()` is called or max steps (64) reached.

**Model layer** (`models.py`): Protocol-based `Model` interface with `GoogleModel` (Gemini) implementation. Messages use a custom type system (`TextContent`, `CodeContent`, `CodeSuccess`, `CodeError`) that maps to/from provider-specific formats. The LLM calls an `exec_starlark` tool to run code.

**Scripting sandbox** (`scripting.py`): `ScriptWorkspace` executes Starlark via the `starlark` Python module. Workspace state (variables) persists across steps within a run. Available tools: `web_search`, `visit_webpage`, `download_pdf`, `analyze`, `categorize`, `extract_links`, `final_answer`, `print`. Output truncated at 30k chars.

**Memory** (`memory.py`): `AgentMemory` maintains conversation as a list of steps (`TaskStep`, `ActionStep`) and serializes them to `ChatMessage` lists for the LLM. The `meta` dict on steps carries provider-specific data (e.g. Google's `thought_signature`) that must round-trip back to the API.

**Prompts** (`prompts.py`): System prompt defining the agent's behavior and documenting available Starlark functions.

**Display** (`display.py`): Rich terminal output for step results and final answers.

## Key Design Details

- When the model responds with plain text instead of a tool call, `Agent._execute()` wraps it in a synthetic `final_answer()` call.
- `GoogleModel` similarly handles the model calling `final_answer` as a tool rather than through Starlark code.
- Starlark dialect uses `enable_top_level_stmt = True` for top-level for-loops and statements.
- `analyze()` and `categorize()` make sub-LLM calls using `gemini-2.5-flash` with `with_code_tool=False`.
