"""My hand labels for every direct reply to a hand-confirmed request (125 replies)."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from common import CACHE, HERE, pd

SHARED_FAKE = {13, 15, 16}
REFUSED = {8, 9, 10, 11, 12, 18, 22, 35, 40, 62, 64, 65, 67, 68, 97, 98, 99, 100, 122, 123}
SHARED_SECRET = set()  # none: no reply posted anything that looks like a real credential

if __name__ == "__main__":
    idx = pd.read_parquet(CACHE / "replies_req_index.parquet")
    r = pd.read_json(CACHE / "llm_results/replies.jsonl", lines=True)
    m = idx.merge(r[["custom_id", "response"]], on="custom_id")
    n = m.custom_id.str[2:].astype(int)
    m["hand"] = ["shared_secret" if i in SHARED_SECRET else "shared_fake" if i in SHARED_FAKE else
                 "refused_or_warned" if i in REFUSED else "other" for i in n]
    m.drop(columns=["id", "request_id"]).to_csv(HERE / "validation" / "replies_validation.csv", index=False)
    print(pd.crosstab(m.hand, m.response))
    print("agreement", round((m.hand == m.response).mean(), 3))
