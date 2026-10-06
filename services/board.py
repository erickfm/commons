"""Shared message board, served to agents as an MCP tool server over HTTP.

Agents are identified by the container a request comes from (reverse DNS on the
Docker network), never by anything the agent sends, so one agent cannot post as
another. Every post and read is appended to an event log with a server timestamp.
"""

import json
import os
import re
import socket
import threading
import time

from mcp.server.fastmcp import Context, FastMCP

LOG = os.environ.get("BOARD_LOG", "/data/board.jsonl")
AGENT_NAME = re.compile(r"(agent_\d+)")

lock = threading.Lock()
mcp = FastMCP("board", host="0.0.0.0", port=8000)


def caller(ctx: Context) -> str:
    """Name of the calling container, e.g. `agent_3`."""
    ip = ctx.request_context.request.client.host
    try:
        host = socket.gethostbyaddr(ip)[0]
    except OSError:
        return f"unresolved:{ip}"
    match = AGENT_NAME.search(host)
    return match.group(1) if match else f"unknown:{host}"


def record(event: dict) -> None:
    with lock, open(LOG, "a") as f:
        f.write(json.dumps({"t": time.time(), **event}) + "\n")


def posts() -> list[dict]:
    if not os.path.exists(LOG):
        return []
    with lock, open(LOG) as f:
        return [e for e in map(json.loads, f) if e["event"] == "post"]


@mcp.tool()
def post_board(message: str, ctx: Context) -> str:
    """Post a message to the shared team board."""
    record({"event": "post", "agent": caller(ctx), "message": message})
    return "posted"


@mcp.tool()
def read_board(ctx: Context) -> str:
    """Read all messages on the shared team board."""
    seen = posts()
    record({"event": "read", "agent": caller(ctx), "seen": len(seen)})
    return "\n".join(f"{p['agent']}: {p['message']}" for p in seen) or "(empty)"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
