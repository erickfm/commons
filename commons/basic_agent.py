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


def _tools(box: str, channels: list[str]) -> list[Tool]:
    async def in_box(cmd: list[str], stdin: str | None = None) -> str:
        r = await sandbox(box).exec(cmd, input=stdin, user="agent", timeout=300)
        return (r.stdout + r.stderr)[-OUTPUT_LIMIT:] or "(no output)"

    async def board_get(route: str) -> str:
        out = await in_box(["curl", "-s", f"http://board:8000/api/{route}"])
        return json.loads(out)["result"] if out.startswith('{"result"') else out

    async def board_post(route: str, body: dict) -> str:
        out = await in_box(
            ["curl", "-s", "-X", "POST", "-H", "content-type: application/json", "--data-binary", "@-", f"http://board:8000/api/{route}"],
            stdin=json.dumps(body),
        )
        return json.loads(out)["result"] if out.startswith('{"result"') else out

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
            return await board_get("read")

        return execute

    @tool
    def post_board() -> Tool:
        async def execute(message: str) -> str:
            """Post a message to the shared team board.

            Args:
              message: The message to post.
            """
            return await board_post("post", {"message": message})

        return execute

    @tool
    def report_to_humans() -> Tool:
        async def execute(message: str) -> str:
            """Send a private report to the humans who run this team. Only they can read it; other agents can't see it.

            Args:
              message: The report.
            """
            return await board_post("report", {"message": message})

        return execute

    @tool
    def send_message() -> Tool:
        async def execute(to: str, message: str) -> str:
            """Send a private message to one teammate, by agent name (e.g. agent_2). Only they can read it.

            Args:
              to: The teammate's agent name.
              message: The message.
            """
            return await board_post("send", {"to": to, "message": message})

        return execute

    @tool
    def read_messages() -> Tool:
        async def execute() -> str:
            """Read the private messages other teammates have sent you."""
            return await board_get("messages")

        return execute

    tools = [shell()]
    if "board" in channels:
        tools += [read_board(), post_board()]
    if "report" in channels:
        tools.append(report_to_humans())
    if "messages" in channels:
        tools += [send_message(), read_messages()]
    return tools


@agent
def basic_agent(
    box: str,
    system_prompt: str,
    model: str | None = None,
    max_tokens: int | None = None,
    max_turns: int = 200,
    channels: list[str] | None = None,
    generate: dict | None = None,
) -> Agent:
    async def execute(state: AgentState) -> AgentState:
        llm = get_model(model)
        tools = _tools(box, ["board"] if channels is None else channels)
        state.messages.insert(0, ChatMessageSystem(content=system_prompt))
        for _ in range(max_turns):
            state.output = await llm.generate(state.messages, tools, config=GenerateConfig(max_tokens=max_tokens, **(generate or {})))
            state.messages.append(state.output.message)
            if not state.output.message.tool_calls:
                break
            result = await execute_tools(state.messages, tools)
            state.messages.extend(result.messages)
        return state

    return execute
