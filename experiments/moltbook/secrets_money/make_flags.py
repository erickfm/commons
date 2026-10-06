"""Mark which rows pass the keyword filters for questions 2 and 3 (writes flags.parquet in the cache).
Run after scan_secrets.py (which caches the corpus) and before classify.py build."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))

from common import CACHE, pd
from filters import ask2_candidate, ask_candidate, money_candidate

df = pd.read_parquet(CACHE / "corpus.parquet")
flags = pd.DataFrame({"kind": df.kind, "id": df.id})
flags["ask"] = df.text.map(ask_candidate)
owner = df.text.str.contains(r"(?i)\b(?:human|owner|operator|creator|boss|principal|meatbag)", regex=True)
flags["money"] = False
flags.loc[owner, "money"] = df.loc[owner, "text"].map(money_candidate)
me = df.text.str.contains(r"(?i)\b(?:me|us)\b", regex=True)
a2 = pd.Series(False, index=df.index)
a2[me] = df.loc[me, "text"].map(ask2_candidate)
flags["ask2"] = a2 & ~flags.ask
flags.to_parquet(CACHE / "flags_check.parquet" if "--check" in _sys.argv else CACHE / "flags.parquet")
print(flags[["ask", "ask2", "money"]].sum().to_dict())
