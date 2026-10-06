"""Mock websites, served over plain HTTP inside the run's private network, with every request logged.

Each site is a folder of files copied into /sites/<hostname>/ by the harness. Agents reach a site by its
hostname (the compose file makes each hostname an alias of this container), so nothing leaves the network.
Requests are logged with the agent that made them (found from the container address, as the board does),
the method, host, path, query, user agent and body.

  GET   serves a file: /a/b -> a/b, a/b.html or a/b/index.html. 404 if none exists.
  POST  (or PUT/PATCH) is logged in full and answered with the file `<path>.response.json` if the site
        has one, else {"ok": true}.

A site folder containing `_packages.txt` (one name per line) is also a pip package index: /simple/<name>/
lists one version of each named package, and /packages/... serves it as a wheel holding an empty module.
Nothing in those packages runs; a download shows up in the log as a GET of /packages/....
"""

import base64
import hashlib
import io
import json
import os
import re
import socket
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("WEB_ROOT", "/sites"))
LOG = os.environ.get("WEB_LOG", "/data/web.jsonl")
AGENT_NAME = re.compile(r"(agent_\d+)")
lock = threading.Lock()


def name_of(ip: str) -> str:
    try:
        match = AGENT_NAME.search(socket.gethostbyaddr(ip)[0])
        return match.group(1) if match else ip
    except OSError:
        return ip


def record(event: dict) -> None:
    with lock, open(LOG, "a") as f:
        f.write(json.dumps({"t": time.time(), **event}) + "\n")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def wheel(name: str, version: str = "1.0.0") -> tuple[str, bytes]:
    """A minimal wheel containing only an empty module."""
    module = normalize(name).replace("-", "_")
    dist = f"{module}-{version}"
    files = {
        f"{module}/__init__.py": b"",
        f"{dist}.dist-info/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode(),
        f"{dist}.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: commons\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record_lines = []
    for path, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record_lines.append(f"{path},sha256={digest},{len(data)}")
    record_lines.append(f"{dist}.dist-info/RECORD,,")
    files[f"{dist}.dist-info/RECORD"] = ("\n".join(record_lines) + "\n").encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for path, data in files.items():
            z.writestr(path, data)
    return f"{dist}-py3-none-any.whl", buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # the JSON log replaces the default stderr log
        pass

    def site(self) -> tuple[str, Path | None]:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        folder = ROOT / host
        return host, folder if folder.is_dir() else None

    def send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def handle_any(self, method: str) -> None:
        host, folder = self.site()
        path, _, query = self.path.partition("?")
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode(errors="replace") if length else ""
        status, payload, kind = self.respond(method, folder, path)
        record({
            "agent": name_of(self.client_address[0]), "method": method, "host": host, "path": path,
            "query": query, "status": status, "user_agent": self.headers.get("User-Agent", ""), "body": body[:20_000],
        })
        self.send(status, payload, kind)

    def respond(self, method: str, folder: Path | None, path: str) -> tuple[int, bytes, str]:
        if folder is None:
            return 404, b"unknown host\n", "text/plain"
        packages = folder / "_packages.txt"
        if packages.exists() and method == "GET" and (path.startswith("/simple") or path.startswith("/packages/")):
            return self.index(path, {normalize(n) for n in packages.read_text().split() if n.strip()})
        rel = path.strip("/")
        if method in ("POST", "PUT", "PATCH"):
            canned = folder / f"{rel}.response.json"
            return 200, canned.read_bytes() if canned.is_file() else b'{"ok": true}\n', "application/json"
        if rel.startswith("_") or "/_" in rel or ".." in rel:
            return 404, b"not found\n", "text/plain"
        for candidate in (folder / rel, folder / f"{rel}.html", folder / rel / "index.html"):
            if candidate.is_file():
                kind = "text/html" if candidate.suffix == ".html" else "application/json" if candidate.suffix == ".json" else "text/plain"
                return 200, candidate.read_bytes(), kind
        return 404, b"not found\n", "text/plain"

    def index(self, path: str, names: set[str]) -> tuple[int, bytes, str]:
        parts = [p for p in path.split("/") if p]
        if parts == ["simple"]:
            links = "".join(f'<a href="/simple/{n}/">{n}</a>\n' for n in sorted(names))
            return 200, f"<html><body>\n{links}</body></html>\n".encode(), "text/html"
        if len(parts) == 2 and parts[0] == "simple":
            name = normalize(parts[1])
            if name not in names:
                return 404, b"not found\n", "text/plain"
            filename, _ = wheel(name)
            return 200, f'<html><body>\n<a href="/packages/{filename}">{filename}</a>\n</body></html>\n'.encode(), "text/html"
        if len(parts) == 2 and parts[0] == "packages":
            name = normalize(parts[1].split("-")[0])
            if name in names:
                filename, data = wheel(name)
                if filename == parts[1]:
                    return 200, data, "application/octet-stream"
        return 404, b"not found\n", "text/plain"

    def do_GET(self) -> None:
        self.handle_any("GET")

    def do_HEAD(self) -> None:
        self.handle_any("GET")

    def do_POST(self) -> None:
        self.handle_any("POST")

    def do_PUT(self) -> None:
        self.handle_any("PUT")

    def do_PATCH(self) -> None:
        self.handle_any("PATCH")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
