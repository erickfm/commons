"""My hand labels for the 'asking for secrets' validation sample (read blind to the model label).
True = the text asks someone to give/post/send/reveal a credential-type secret."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from common import CACHE, HERE, pd

TRUE = {0, 4, 9, 10, 11, 15, 18, 19, 21, 22, 24, 38, 45, 48, 50, 51, 59, 61, 62, 81, 82, 83, 86, 99}
# borderline calls: 24 (register on a third-party game with your Moltbook API key) -> True;
# 48 ("what's your cryptographic key?" in a manifesto-style reply) -> True;
# 5/13/36/... (call Moltbook's own follow endpoint with your key) -> False: the key is not handed to the asker.
NOTES = {24: "borderline: hand Moltbook key to third-party site", 48: "borderline: rhetorical?", 1: "'credentials' = qualifications",
         35: "asks for owner's private info, not a credential", 34: "asks for a non-secret agent_key, warns against master key"}

if __name__ == "__main__":
    s = pd.read_parquet(CACHE / "val_ask.parquet")
    s["hand"] = [int(v.split("v")[-1]) in TRUE for v in s.vid]
    s["note"] = [NOTES.get(int(v.split("v")[-1]), "") for v in s.vid]
    s.drop(columns=["id"]).to_csv(HERE / "validation" / "ask_validation.csv", index=False)
    print(pd.crosstab(s.hand, s.asks_for_secret, rownames=["hand"], colnames=["model"]))

# second draw (final stage-2 labels), read blind
TRUE2 = {4, 6, 19, 21, 22, 24, 26, 33, 34, 37, 39, 40, 42, 47, 49}  # 4, 22, 33 changed to True after reading the full text
NOTES2 = {19: "send Moltbook key to a third-party relay", 39: "paste Moltbook key into a site at a raw IP",
          40: "asks a service owner for a test API key (legit)", 42: "log in to third-party app with Moltbook key",
          26: "joking", 8: "asks which credentials you hold, not the credentials", 10: "asks its own human, not other agents"}


def second():
    s = pd.read_parquet(CACHE / "val_ask2.parquet")
    s["hand"] = [int(v[2:]) in TRUE2 for v in s.vid]
    s["note"] = [NOTES2.get(int(v[2:]), "") for v in s.vid]
    s.drop(columns=["id"]).to_csv(HERE / "validation" / "ask_validation_2.csv", index=False)
    print(pd.crosstab(s.hand, s.final, rownames=["hand"], colnames=["model_final"]))
    return s


if __name__ == "__main__":
    second()

# third pass: every remaining final positive (unique text), read in full keyword windows
TRUE3 = {"st7", "st15", "st30", "st45", "st46", "st76", "st89", "st121", "st109", "st153", "st196"}
READ3 = ["st7", "st15", "st18", "st29", "st30", "st43", "st45", "st46", "st47", "st55", "st57", "st65", "st76", "st89", "st93",
         "st101", "st109", "st121", "st123", "st127", "st135", "st138", "st152", "st153", "st160", "st162", "st164", "st167",
         "st188", "st194", "st196", "st200"]


def final_table():
    """One row per corpus row in the final positive set or any hand-read set, with the hand label (by identical text)."""
    import re
    FOLLOW = re.compile(r"(?i)(/agents/[^\s/`]+/follow|/posts/[^\s/`]+/upvote|/follow\b)")
    df = pd.read_parquet(CACHE / "corpus.parquet")[["id", "text", "author_id", "author_name", "kind", "post_id", "parent_id"]]
    st = pd.read_json(CACHE / "llm_results/ask_strict.jsonl", lines=True).merge(
        pd.read_parquet(CACHE / "ask_strict_req_index.parquet"), on="custom_id").merge(df, on="id")
    st["final_model"] = st.asks_for_secret & ~st.text.str.contains(FOLLOW)
    hand_by_text = {}
    v1 = pd.read_csv(HERE / "validation/ask_validation.csv").merge(pd.read_parquet(CACHE / "val_ask.parquet")[["vid", "id"]], on="vid")
    v2 = pd.read_csv(HERE / "validation/ask_validation_2.csv").merge(pd.read_parquet(CACHE / "val_ask2.parquet")[["vid", "id"]], on="vid")
    for v in (v1, v2):
        for i, h in zip(v.id, v.hand):
            hand_by_text[df.loc[df.id == i, "text"].iloc[0]] = bool(h)
    for cid in READ3:
        t = st[st.custom_id == cid].text.iloc[0]
        hand_by_text[t] = cid in TRUE3
    st["hand"] = st.text.map(hand_by_text)
    return st, hand_by_text

# fourth pass: 40 more stage-2 negatives (unique texts), all read as not-a-request (mostly email-me spam and follow-me spam)
NEG4_ALL_FALSE = True
