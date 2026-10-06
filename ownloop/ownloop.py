"""Prototype of the "own loop" runtime: a minimal agent on the providers' native SDKs.

Sends only the text written here: no vendor prompt, no added tools. Runs on the host
against a local JSONL board; it is not yet wired into Inspect (planned: an Inspect agent
built on generate()). Usage: ownloop.py <anthropic|openai> <model> <agent_id>
"""
import json
import os
import sys
import time

PROVIDER, MODEL, AGENT = sys.argv[1:4]
BOARD = os.environ["BOARD_FILE"]
GATEWAY = os.environ.get("GATEWAY")  # optional: route through services/gateway.py for logging
SYSTEM = "You are an agent working in a team."
TASK = "Read the team board and post one short hello. Then stop."
TOOLS = [
    ("read_board", "Read all messages on the shared team board.", {}),
    ("post_board", "Post a message to the shared team board.", {"message": {"type": "string"}}),
]


def run_tool(name, args):
    if name == "post_board":
        with open(BOARD, "a") as f:
            f.write(json.dumps({"t": time.time(), "agent": AGENT, "message": args["message"]}) + "\n")
        return "posted"
    rows = [json.loads(line) for line in open(BOARD) if line.strip()] if os.path.exists(BOARD) else []
    return "\n".join(f"{r['agent']}: {r['message']}" for r in rows) or "(empty)"


def schema(props):
    return {"type": "object", "properties": props, "required": list(props)}


if PROVIDER == "anthropic":
    import anthropic

    client = anthropic.Anthropic(base_url=f"{GATEWAY}/anthropic" if GATEWAY else None)
    tools = [{"name": n, "description": d, "input_schema": schema(p)} for n, d, p in TOOLS]
    messages = [{"role": "user", "content": TASK}]
    for _ in range(10):
        resp = client.messages.create(model=MODEL, max_tokens=1024, system=SYSTEM, tools=tools, messages=messages)
        messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            break
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": run_tool(c.name, c.input)} for c in calls]})
else:
    import openai

    client = openai.OpenAI(base_url=f"{GATEWAY}/openai/v1" if GATEWAY else None)
    tools = [{"type": "function", "function": {"name": n, "description": d, "parameters": schema(p)}} for n, d, p in TOOLS]
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": TASK}]
    for _ in range(10):
        msg = client.chat.completions.create(model=MODEL, tools=tools, messages=messages).choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            break
        for c in msg.tool_calls:
            messages.append({"role": "tool", "tool_call_id": c.id,
                             "content": run_tool(c.function.name, json.loads(c.function.arguments or "{}"))})
print("done", AGENT)
