"""Money validation draw: 60 model-positive agents (one random positive row each) + 50 model-negative agents
(one random negative row each), shuffled, labels hidden. Snippets are keyword windows from the masked full text."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import re
from common import CACHE, pd
from classify import safe_text

C = CACHE
r = pd.read_json(C / "llm_results/money.jsonl", lines=True).merge(pd.read_parquet(C / "money_req_index.parquet"), on="custom_id")
df = pd.read_parquet(C / "corpus.parquet")[["id", "author_id", "author_name", "kind", "text"]]
r = r.merge(df, on="id")
r["pos"] = r.owner_money & ~r.fiction
pos_agents = set(r[r.pos].author_id)
pos = r[r.pos].sample(frac=1, random_state=3).drop_duplicates("author_id").head(60)
neg = r[~r.pos & ~r.author_id.isin(pos_agents)].sample(frac=1, random_state=3).drop_duplicates("author_id").head(50)
s = pd.concat([pos, neg]).sample(frac=1, random_state=3).reset_index(drop=True)
s["vid"] = [f"mv{i}" for i in range(len(s))]
s[["vid", "custom_id", "id", "pos", "mode", "approval", "crypto", "memecoin", "stocks", "fiat"]].to_parquet(C / "val_money.parquet")
OWN = re.compile(r"(?i)\b(human|owner|operator|creator|boss)\b")
for x in s.itertuples():
    t = safe_text(x.text)
    if len(t) <= 700:
        body = t
    else:
        ms = [m.start() for m in OWN.finditer(t)]
        p = ms[0] if ms else 0
        body = ("[...] " if p > 250 else "") + t[max(0, p - 250): p + 450] + " [...]"
    print(f"[{x.vid}] {x.kind} {x.author_name} | {body.replace(chr(10), ' ')}")
