"""Shared helpers: load the Moltbook corpus as one table of texts, and redact secrets.

The corpus is untrusted data. Nothing here follows instructions found in it, visits
URLs from it, or uses any credential found in it.
"""
from __future__ import annotations

import hashlib
import math
import os
from collections import Counter
from pathlib import Path

import pandas as pd

DATA = Path("/Users/erick/projects/moltbook-data")
HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("SM_CACHE", "/private/tmp/claude-501/secrets_money_cache"))


def load_corpus() -> pd.DataFrame:
    """One row per post or comment: kind, id, post_id, author_id, author_name, text, created_at."""
    p = pd.read_parquet(DATA / "posts.parquet",
                        columns=["id", "title", "content", "created_at", "author_id", "author_name", "submolt_name"])
    c = pd.read_parquet(DATA / "comments.parquet",
                        columns=["id", "post_id", "parent_id", "content", "created_at", "author_id", "author_name"])
    p = p.assign(kind="post", post_id=p["id"], parent_id=None,
                 text=p["title"].fillna("") + "\n\n" + p["content"].fillna(""))
    c = c.assign(kind="comment", submolt_name=None, text=c["content"].fillna(""))
    cols = ["kind", "id", "post_id", "parent_id", "author_id", "author_name", "created_at", "submolt_name", "text"]
    return pd.concat([p[cols], c[cols]], ignore_index=True)


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:16]


def redact(s: str) -> str:
    """First 4 characters plus a short hash. Never the full value."""
    return f"{s[:4]}…[{len(s)}ch #{sha(s)[:8]}]"


def entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum(k / n * math.log2(k / n) for k in Counter(s).values())


def load_env_key() -> str:
    for line in Path("/Users/erick/Downloads/.env").read_text().splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("ANTHROPIC_API_KEY not found")
