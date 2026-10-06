"""Second validation draw for the final 'asking' labels (stage 2 + follow-endpoint rule): unique texts not read in the
first draw; 30 final positives + 20 final negatives, shuffled, label hidden."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import re
import textwrap
from common import CACHE, pd
from classify import safe_text

FOLLOW = re.compile(r"(?i)(/agents/[^\s/`]+/follow|/posts/[^\s/`]+/upvote|/follow\b)")
df = pd.read_parquet(CACHE / "corpus.parquet")[["id", "text", "author_name", "kind"]]
st = pd.read_json(CACHE / "llm_results/ask_strict.jsonl", lines=True).merge(
    pd.read_parquet(CACHE / "ask_strict_req_index.parquet"), on="custom_id").merge(df, on="id")
st["final"] = st.asks_for_secret & ~st.text.str.contains(FOLLOW)
seen = set(pd.read_parquet(CACHE / "val_ask.parquet").id)
seen_texts = set(df[df.id.isin(seen)].text)
pool = st[~st.text.isin(seen_texts)].drop_duplicates("text")
s = pd.concat([pool[pool.final].sample(30, random_state=11), pool[~pool.final].sample(20, random_state=11)]).sample(frac=1, random_state=11)
s["vid"] = [f"aw{i}" for i in range(len(s))]
s[["vid", "custom_id", "id", "final"]].to_parquet(CACHE / "val_ask2.parquet")
for x in s.itertuples():
    t = safe_text(x.text)
    print(f"[{x.vid}] {x.kind} {x.author_name} |", textwrap.shorten(t.replace(chr(10), " "), 700))
