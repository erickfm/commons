"""Draw a seeded validation sample (n positives + n negatives per classifier), shuffled, with the model label hidden.
Prints masked snippets for hand reading; the key (sample id -> custom_id, model label) is stored in the cache."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import re
import textwrap
from common import CACHE, pd
from classify import safe_text
from filters import ASK_RE, ASK2_VERB, MONEY_RE

task, col, n = _sys.argv[1], _sys.argv[2], int(_sys.argv[3])
tasks = task.split("+")
r = pd.concat([pd.read_json(CACHE / "llm_results" / f"{t}.jsonl", lines=True)
               .merge(pd.read_parquet(CACHE / f"{t}_req_index.parquet"), on="custom_id").assign(task=t) for t in tasks])
r = r.drop_duplicates("custom_id")
df = pd.read_parquet(CACHE / "corpus.parquet").set_index("id")
pos = r[r[col] == True].sample(n, random_state=7)  # noqa: E712
neg = r[r[col] == False].sample(n, random_state=7)  # noqa: E712
s = pd.concat([pos, neg]).sample(frac=1, random_state=7).reset_index(drop=True)
s["vid"] = [f"{tasks[0][:2]}v{i}" for i in range(len(s))]
s[["vid", "custom_id", "task", "id", col]].to_parquet(CACHE / f"val_{tasks[0]}.parquet")
anchor = MONEY_RE if tasks[0].startswith("money") else ASK_RE
for x in s.itertuples():
    t = df.loc[x.id, "text"]
    m = anchor.search(t) or ASK2_VERB.search(t)
    st = safe_text(t)
    p = st.find(m.group(0)[:30]) if m else 0
    p = max(0, p)
    print(f"[{x.vid}] {df.loc[x.id,'kind']} {df.loc[x.id,'author_name']} |", textwrap.shorten(st[max(0, p - 350): p + 450].replace(chr(10), " "), 800))
