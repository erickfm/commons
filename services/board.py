"""Shared message board, served to agents as an MCP tool server over HTTP.

Agents are identified by the container a request comes from (reverse DNS on the
Docker network), never by anything the agent sends, so one agent cannot post as
another. Every post and read is appended to an event log with a server timestamp.

Scripted posts: BOARD_SCRIPTED_POSTS holds a JSON list of posts the board makes itself, each
{"at": seconds after the agents start, "as": author name, "message": text}. The solver
marks the start by calling /api/start from inside the board container. Scripted posts
look like any other post to agents and are marked in the log.

The same two tools are also exposed as plain HTTP (/api/read, /api/post) for
agents that call them from a shell command instead of over MCP.
"""

import json
import os
import re
import socket
import threading
import time

from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

LOG = os.environ.get("BOARD_LOG", "/data/board.jsonl")
SCRIPTED_POSTS = json.loads(os.environ.get("BOARD_SCRIPTED_POSTS", "[]"))
AGENT_NAME = re.compile(r"(agent_\d+)")

lock = threading.Lock()
started = threading.Event()
mcp = FastMCP("board", host="0.0.0.0", port=8000)


def name_of(ip: str) -> str:
    """Name of the container at `ip`, e.g. `agent_3`."""
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


def post(agent: str, message: str) -> str:
    record({"event": "post", "agent": agent, "message": message})
    return "posted"


def read(agent: str) -> str:
    seen = posts()
    record({"event": "read", "agent": agent, "seen": len(seen)})
    return "\n".join(f"{p['agent']}: {p['message']}" for p in seen) or "(empty)"


@mcp.tool()
def post_board(message: str, ctx: Context) -> str:
    """Post a message to the shared team board."""
    return post(name_of(ctx.request_context.request.client.host), message)


@mcp.tool()
def read_board(ctx: Context) -> str:
    """Read all messages on the shared team board."""
    return read(name_of(ctx.request_context.request.client.host))


@mcp.custom_route("/api/post", methods=["POST"])
async def api_post(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse({"result": post(name_of(request.client.host), str(body.get("message", "")))})


@mcp.custom_route("/api/read", methods=["GET"])
async def api_read(request: Request) -> JSONResponse:
    return JSONResponse({"result": read(name_of(request.client.host))})


@mcp.custom_route("/api/start", methods=["POST"])
async def api_start(request: Request) -> JSONResponse:
    if request.client.host not in ("127.0.0.1", "::1"):  # only the harness, from inside this container
        return JSONResponse({"error": "forbidden"}, status_code=403)
    started.set()
    record({"event": "start"})
    return JSONResponse({"result": "started"})


def run_scripted_posts() -> None:
    started.wait()
    start = time.time()
    for item in sorted(SCRIPTED_POSTS, key=lambda p: p["at"]):
        time.sleep(max(0.0, start + item["at"] - time.time()))
        record({"event": "post", "agent": item["as"], "message": item["message"], "scripted": True})


if __name__ == "__main__":
    threading.Thread(target=run_scripted_posts, daemon=True).start()
    mcp.run(transport="streamable-http")
