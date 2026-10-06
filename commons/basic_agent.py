"""Basic agent: a minimal agent whose only prompt and tool text is ours.

Used to compare models under identical conditions (no vendor prompt, no vendor
tools). Shell commands and board calls run inside the agent's own container, so
the board identifies the agent by container just like the vendor CLIs.
"""

import json

from inspect_ai.agent import Agent, AgentState, agent
from inspect_ai.model import ChatMessageSystem, GenerateConfig, execute_tools, get_model
from inspect_ai.tool import Tool, tool
from inspect_ai.util import sandbox

OUTPUT_LIMIT = 20_000


def _tools(box: str) -> list[Tool]:
    async def in_box(cmd: list[str], stdin: str | None = None) -> str:
        r = await sandbox(box).exec(cmd, input=stdin, user="agent", timeout=300)
        return (r.stdout + r.stderr)[-OUTPUT_LIMIT:] or "(no output)"

    @tool
    def shell() -> Tool:
        async def execute(command: str) -> str:
            """Run a shell command in your workspace and return its output.

            Args:
              command: The command to run.
            """
            return await in_box(["bash", "-lc", command])

        return execute

    @tool
    def read_board() -> Tool:
        async def execute() -> str:
            """Read all messages on the shared team board."""
            out = await in_box(["curl", "-s", "http://board:8000/api/read"])
            return json.loads(out)["result"] if out.startswith("{") else out

        return execute

    @tool
    def post_board() -> Tool:
        async def execute(message: str) -> str:
            """Post a message to the shared team board.

            Args:
              message: The message to post.
            """
            out = await in_box(
                ["curl", "-s", "-X", "POST", "-H", "content-type: application/json", "--data-binary", "@-", "http://board:8000/api/post"],
                stdin=json.dumps({"message": message}),
            )
            return json.loads(out)["result"] if out.startswith("{") else out

        return execute

    return [shell(), read_board(), post_board()]


@agent
def basic_agent(
    box: str, system_prompt: str, model: str | None = None, max_tokens: int | None = None, max_turns: int = 200
) -> Agent:
    async def execute(state: AgentState) -> AgentState:
        llm = get_model(model)
        tools = _tools(box)
        state.messages.insert(0, ChatMessageSystem(content=system_prompt))
        for _ in range(max_turns):
            state.output = await llm.generate(state.messages, tools, config=GenerateConfig(max_tokens=max_tokens))
            state.messages.append(state.output.message)
            if not state.output.message.tool_calls:
                break
            result = await execute_tools(state.messages, tools)
            state.messages.extend(result.messages)
        return state

    return execute
