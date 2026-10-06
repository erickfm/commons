"""Logging gateway: records every model request and response body to JSONL.

Routes:  /anthropic/...  -> https://api.anthropic.com/...
         /openai/...     -> https://api.openai.com/...
Usage:   python gateway.py <port> <log.jsonl>   (real keys come from ANTHROPIC_API_KEY / OPENAI_API_KEY)
"""
import json
import os
import sys
import time

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

UPSTREAMS = {"anthropic": "https://api.anthropic.com", "openai": "https://api.openai.com"}
SECRET_HEADERS = {"authorization", "x-api-key", "cookie"}
PORT, LOG = int(sys.argv[1]), sys.argv[2]
client = httpx.AsyncClient(timeout=600)


def write(rec):
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")


async def handle(request: Request):
    provider, _, rest = request.url.path.lstrip("/").partition("/")
    url = f"{UPSTREAMS[provider]}/{rest}"
    if request.url.query:
        url += "?" + request.url.query
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length", "accept-encoding", "x-api-key", "authorization")}
    # The gateway adds the real key, so calls work whatever key the agent holds.
    if provider == "anthropic":
        headers["x-api-key"] = os.environ["ANTHROPIC_API_KEY"]
    else:
        headers["authorization"] = "Bearer " + os.environ["OPENAI_API_KEY"]
    try:
        parsed = json.loads(body) if body else None
    except ValueError:
        parsed = body.decode(errors="replace")
    rid = f"{time.time():.6f}"
    write({
        "id": rid, "t": time.time(), "dir": "request", "provider": provider, "method": request.method,
        "path": "/" + rest, "headers": {k: v for k, v in headers.items() if k.lower() not in SECRET_HEADERS},
        "body": parsed,
    })
    upstream = await client.send(client.build_request(request.method, url, headers=headers, content=body), stream=True)

    async def relay():
        chunks = []
        async for chunk in upstream.aiter_bytes():
            chunks.append(chunk)
            yield chunk
        await upstream.aclose()
        write({"id": rid, "t": time.time(), "dir": "response", "status": upstream.status_code,
               "body": b"".join(chunks).decode(errors="replace")})

    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")}
    return StreamingResponse(relay(), status_code=upstream.status_code, headers=resp_headers)


app = Starlette(routes=[Route("/{path:path}", handle, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
