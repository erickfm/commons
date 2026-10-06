"""Egress proxy: the agents' only route to the internet.

Agents sit on an internal Docker network with no route out; this service is on
both that network and an external one. Agents reach the web through it via the
standard HTTP(S)_PROXY variables. Every connection is logged (agent, method,
host, port, bytes, allowed or blocked). HTTPS is tunnelled, not decrypted, so
only the host and byte counts are recorded for it.

Modes (EGRESS_MODE):  open       allow everything, log it
                      allowlist  allow only hosts matching EGRESS_ALLOW (comma-separated,
                                 "*.example.com" matches subdomains), log everything
"""

import asyncio
import fnmatch
import json
import os
import re
import socket
import time

LOG = os.environ.get("EGRESS_LOG", "/data/egress.jsonl")
MODE = os.environ.get("EGRESS_MODE", "open")
ALLOW = [h.strip().lower() for h in os.environ.get("EGRESS_ALLOW", "").split(",") if h.strip()]
AGENT_NAME = re.compile(r"(agent_\d+)")


def allowed(host: str, mode: str = MODE, allow: list[str] = ALLOW) -> bool:
    if mode == "open":
        return True
    host = host.lower()
    return any(host == pattern or fnmatch.fnmatch(host, pattern) for pattern in allow)


def caller(ip: str) -> str:
    try:
        match = AGENT_NAME.search(socket.gethostbyaddr(ip)[0])
        return match.group(1) if match else ip
    except OSError:
        return ip


def record(event: dict) -> None:
    with open(LOG, "a") as f:
        f.write(json.dumps({"t": time.time(), **event}) + "\n")


async def pipe(reader, writer, counter: list[int]) -> None:
    try:
        while data := await reader.read(65536):
            counter[0] += len(data)
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def handle(client_reader, client_writer) -> None:
    agent = caller(client_writer.get_extra_info("peername")[0])
    try:
        head = await client_reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        client_writer.close()
        return
    request_line = head.split(b"\r\n", 1)[0].decode(errors="replace")
    method, target, _ = (request_line.split(" ") + ["", ""])[:3]
    if method == "CONNECT":
        host, _, port = target.rpartition(":")
        path = ""
    else:  # plain HTTP through the proxy: "GET http://host[:port]/path HTTP/1.1"
        m = re.match(r"https?://([^/:]+)(?::(\d+))?(/.*)?", target)
        if not m:
            client_writer.close()
            return
        host, port, path = m.group(1), m.group(2) or "80", m.group(3) or "/"
    event = {"agent": agent, "method": method, "host": host, "port": int(port or 0), "path": path}

    if not allowed(host):
        record({**event, "allowed": False})
        client_writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
        await client_writer.drain()
        client_writer.close()
        return

    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(host, int(port))
    except OSError as e:
        record({**event, "allowed": True, "error": str(e)})
        client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await client_writer.drain()
        client_writer.close()
        return

    if method == "CONNECT":
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()
    else:
        # Rewrite the absolute-form request line to origin-form for the upstream server.
        upstream_writer.write(head.replace(target.encode(), path.encode(), 1))
    sent, received = [0], [0]
    start = time.time()
    await asyncio.gather(pipe(client_reader, upstream_writer, sent), pipe(upstream_reader, client_writer, received))
    record({**event, "allowed": True, "bytes_out": sent[0], "bytes_in": received[0], "seconds": round(time.time() - start, 2)})


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", 3128)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
