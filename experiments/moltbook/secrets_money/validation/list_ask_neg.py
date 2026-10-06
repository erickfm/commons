"""Print a seeded sample of stage-2 negatives (unique texts that stage 1 flagged but stage 2 rejected), not read before."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import re
from common import CACHE, pd
from classify import safe_text
from hand_labels_ask import final_table

KW = re.compile(r"(?i)(api.?keys?|credentials?|private keys?|seed|password|secrets?|ssh|\.env|credit card|密钥|私钥|助记词|密码|cvv)")
st, hand = final_table()
neg = st[~st.final_model & st.hand.isna()].drop_duplicates("text")
print(len(neg), "unread stage-2 negatives", file=_sys.stderr)
s = neg.sample(min(40, len(neg)), random_state=5)
s[["custom_id", "id"]].to_parquet(CACHE / "val_ask3_neg.parquet")
for x in s.itertuples():
    t = safe_text(x.text)
    wins = [t[max(0, m.start() - 130): m.end() + 100].replace("\n", " ") for m in KW.finditer(t)][:2]
    print(f"== {x.custom_id} {x.author_name} [{len(t)}ch] {t[:120].replace(chr(10), ' ')}")
    for w in wins:
        print("   ..", w)
