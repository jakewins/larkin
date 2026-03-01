from larkin import memory, models, prompts, scripting
from larkin.output import Output, SilentOutput
from larkin.tools import Tool, generate_tool_docs


class Agent:
    def __init__(
        self,
        model: models.Model,
        system_prompt: str = prompts.SYSTEM_PROMPT,
        tool_functions: list[Tool] | None = None,
        max_steps: int = 64,
        planning_interval: int = 16,
        output: Output = SilentOutput(),
    ):
        if tool_functions is not None:
            resolved_tools = tool_functions
        else:
            from larkin.tools.extras import default_tools

            resolved_tools = default_tools(model)

        self.max_steps = max_steps
        self.model = model
        self.output = output
        self.planning_interval = planning_interval

        # Inject auto-generated tool docs into the system prompt
        tool_docs = generate_tool_docs(resolved_tools)
        populated_prompt = system_prompt.replace("{{tool_docs}}", tool_docs)
        self.memory = memory.AgentMemory(populated_prompt)

        self.workspace = scripting.ScriptWorkspace(resolved_tools)

    def run(self, task: str) -> str:
        self.memory.steps.append(memory.TaskStep(task))
        while True:
            response = self.model.generate(self.memory.to_messages())
            step = self._execute(response)

            self.output.on_step(step)
            self.memory.steps.append(step)

            match step:
                case memory.ActionStep(final_answer=final_answer) if final_answer:
                    self.output.on_final_answer(final_answer)
                    return final_answer

            if len(self.memory.steps) > self.max_steps:
                raise ValueError("reached max steps")

    def _execution_step(self) -> memory.ActionStep:
        response = self.model.generate(self.memory.to_messages())
        step = self._execute(response)
        self.output.on_step(step)
        self.memory.steps.append(step)
        return step

    def _execute(self, response: models.ChatMessage) -> memory.ActionStep:
        """Executes an unvalidated reply from the model"""
        code = response.content[0]
        if isinstance(code, models.TextContent):
            # Some models insist on replying with text as their final output instead of
            # calling final_answer; we paper over that here
            text_no_triple_quotes = code.text.replace("'''", "")
            code = models.CodeContent(
                thought="<< system: model gave text answer, remapping to final_answer >>",
                code=f"final_answer('''{text_no_triple_quotes}''')",
            )
        if not isinstance(code, models.CodeContent):
            raise ValueError(
                f"not implemented: Agent didn't respond with code: {response}"
            )
        match self.workspace.eval(code.code):
            case scripting.ScriptOk(prints=prints, final_answer=final_answer):
                return memory.ActionStep(
                    thought=code.thought,
                    code_action=code.code,
                    outcome="ok",
                    output="\n".join(prints),
                    final_answer=final_answer,
                    meta=code.meta,
                )
            case scripting.ScriptError(prints=prints, error=error):
                return memory.ActionStep(
                    thought=code.thought,
                    code_action=code.code,
                    outcome="failed",
                    output="\n".join(prints),
                    error="\n".join(prints) + "\n" + error,
                    final_answer=None,
                    meta=code.meta,
                )
            case other:
                raise ValueError(f"unexpected eval result: {other}")


if __name__ == "__main__":
    from larkin.models.google import GoogleModel
    from larkin.output import RichOutput

    m = GoogleModel("gemini-2.5-pro")
    agent = Agent(model=m, output=RichOutput())
    agent.run(
        "Find the result of summarizing 452324562364, 124151435 ans 1242534 and then dividing that by 12"
    )
