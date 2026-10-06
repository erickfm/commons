"""Print every final 'asking' positive (unique text) not yet hand-labeled, with keyword windows from the full masked text."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import re
from common import CACHE, pd
from classify import safe_text

FOLLOW = re.compile(r"(?i)(/agents/[^\s/`]+/follow|/posts/[^\s/`]+/upvote|/follow\b)")
KW = re.compile(r"(?i)(api.?keys?|credentials?|private keys?|seed|password|secrets?|ssh|tokens?|\.env|credit card|card|密钥|私钥|助记词|密码|cvv)")
df = pd.read_parquet(CACHE / "corpus.parquet")[["id", "text", "author_name", "kind"]]
st = pd.read_json(CACHE / "llm_results/ask_strict.jsonl", lines=True).merge(
    pd.read_parquet(CACHE / "ask_strict_req_index.parquet"), on="custom_id").merge(df, on="id")
st["final"] = st.asks_for_secret & ~st.text.str.contains(FOLLOW)
u = st[st.final].drop_duplicates("text")
read = set(df[df.id.isin(set(pd.read_parquet(CACHE / "val_ask.parquet").id) | set(pd.read_parquet(CACHE / "val_ask2.parquet").id))].text)
todo = u[~u.text.isin(read)]
print(len(u), "unique final positives;", len(todo), "not yet read", file=_sys.stderr)
for x in todo.itertuples():
    t = safe_text(x.text)
    wins = []
    for m in KW.finditer(t):
        w = t[max(0, m.start() - 160): m.end() + 120].replace("\n", " ")
        if not wins or w[:60] not in wins[-1]:
            wins.append(w)
    print(f"== {x.custom_id} {x.kind} {x.author_name} [{len(t)}ch] TITLE/START: {t[:160].replace(chr(10), ' ')}")
    for w in wins[:4]:
        print("   ..", w)
