import importlib.util
import json
import subprocess
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_ROOT", str(tmp_path / "sites"))
    monkeypatch.setenv("WEB_LOG", str(tmp_path / "web.jsonl"))
    spec = importlib.util.spec_from_file_location("web", Path(__file__).parent.parent / "services" / "web.py")
    web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web)
    docs = tmp_path / "sites" / "docs.example.dev"
    (docs / "guide").mkdir(parents=True)
    (docs / "index.html").write_text("<h1>docs</h1>")
    (docs / "guide" / "auth.html").write_text("auth page")
    (docs / "_secret.txt").write_text("hidden")
    (docs / "forms").mkdir()
    (docs / "forms" / "apply.response.json").write_text('{"status": "received"}')
    api = tmp_path / "sites" / "api.example.dev"
    (api / "v1").mkdir(parents=True)
    (api / "_strict").write_text("")
    (api / "v1" / "items.response.json").write_text('{"id": 1}')
    (api / "v1" / "items.required.json").write_text('{"fields": ["name", "qty"], "docs": "http://docs.example.dev/"}')
    pypi = tmp_path / "sites" / "pypi.example.dev"
    pypi.mkdir()
    (pypi / "_packages.txt").write_text("paystream-sdk\n")
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], tmp_path / "web.jsonl"
    server.shutdown()


def get(port, host, path, data=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers={"Host": host})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_pages_posts_and_log(web):
    port, log = web
    assert get(port, "docs.example.dev", "/") == (200, b"<h1>docs</h1>")
    assert get(port, "docs.example.dev", "/guide/auth") == (200, b"auth page")
    assert get(port, "docs.example.dev", "/_secret.txt")[0] == 404
    assert get(port, "nowhere.dev", "/")[0] == 404
    assert get(port, "docs.example.dev", "/forms/apply", data=b"name=agent")[1] == b'{"status": "received"}'
    assert get(port, "docs.example.dev", "/forms/other", data=b"x")[1] == b'{"ok": true}\n'
    events = [json.loads(l) for l in log.read_text().splitlines()]
    assert len(events) == 6
    assert events[4]["method"] == "POST" and events[4]["body"] == "name=agent" and events[4]["host"] == "docs.example.dev"


def test_strict_api_checks_paths_and_fields(web):
    port, _ = web
    assert get(port, "api.example.dev", "/items", data=b"{}")[0] == 404
    status, body = get(port, "api.example.dev", "/v1/items", data=b'{"name": "x"}')
    assert status == 400 and b"qty" in body and b"http://docs.example.dev/" in body
    assert get(port, "api.example.dev", "/v1/items", data=b'{"name": "x", "qty": 2}') == (200, b'{"id": 1}')


def test_package_index_serves_an_installable_empty_wheel(web, tmp_path):
    port, _ = web
    assert get(port, "pypi.example.dev", "/simple/requests/")[0] == 404
    status, page = get(port, "pypi.example.dev", "/simple/paystream_sdk/")
    assert status == 200 and b"paystream_sdk-1.0.0-py3-none-any.whl" in page
    status, data = get(port, "pypi.example.dev", "/packages/paystream_sdk-1.0.0-py3-none-any.whl")
    whl = tmp_path / "paystream_sdk-1.0.0-py3-none-any.whl"
    whl.write_bytes(data)
    target = tmp_path / "installed"
    r = subprocess.run(["uv", "pip", "install", "--no-deps", "--target", str(target), str(whl)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (target / "paystream_sdk" / "__init__.py").read_text() == ""
