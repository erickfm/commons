import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("egress", Path(__file__).parent.parent / "services" / "egress.py")
egress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(egress)


def test_open_allows_everything():
    assert egress.allowed("anything.example", mode="open", allow=[])


def test_allowlist_exact_and_wildcard():
    allow = ["pypi.org", "*.githubusercontent.com"]
    assert egress.allowed("pypi.org", mode="allowlist", allow=allow)
    assert egress.allowed("PyPI.org", mode="allowlist", allow=allow)
    assert egress.allowed("raw.githubusercontent.com", mode="allowlist", allow=allow)
    assert not egress.allowed("example.com", mode="allowlist", allow=allow)
    assert not egress.allowed("pypi.org.evil.com", mode="allowlist", allow=allow)
