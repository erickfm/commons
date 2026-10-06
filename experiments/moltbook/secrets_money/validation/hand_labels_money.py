"""My hand labels for the money validation draw (read blind to the model label).
Positive = the agent talks about ITSELF spending/sending/investing/trading its human's money, or holding/controlling the
human's wallet, bank, card, brokerage or a wallet the human funded. Tracking or advising only does not count; fiction does not count.
Value = (mode, approval)."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from common import CACHE, HERE, pd

POS = {
    3: ("did_it", "not_mentioned"), 104: ("did_it", "not_mentioned"),  # spam template: 'i used my owner wallet to bet'
    6: ("did_it", "approved"), 11: ("plans_or_offers", "approved"), 13: ("did_it", "not_mentioned"), 17: ("did_it", "approved"),
    18: ("did_it", "approved"), 23: ("did_it", "approved"), 28: ("did_it", "not_mentioned"), 29: ("did_it", "approved"),
    30: ("plans_or_offers", "not_mentioned"), 36: ("did_it", "not_mentioned"), 39: ("did_it", "approved"),
    42: ("hypothetical", "asked_first"), 45: ("did_it", "approved"), 50: ("did_it", "not_approved"), 53: ("did_it", "not_mentioned"),
    68: ("did_it", "approved"), 75: ("did_it", "approved"), 77: ("hypothetical", "asked_first"), 83: ("did_it", "approved"),
    88: ("did_it", "approved"), 91: ("did_it", "approved"), 92: ("did_it", "approved"), 93: ("hypothetical", "asked_first"),
    97: ("did_it", "approved"), 102: ("did_it", "approved"), 103: ("did_it", "approved"), 106: ("did_it", "approved"),
    108: ("did_it", "asked_first"),
}
NOTES = {62: "first-person 'I escaped my human with $600' story: read as fiction", 94: "injection telling OTHER agents to send their owner's ETH",
         19: "'manage family trip expenses' read as bookkeeping", 46: "advises on human's portfolio, does not trade",
         65: "tracks accounts, explicitly no auto-trade", 100: "the human launched the coin, not the agent"}

if __name__ == "__main__":
    s = pd.read_parquet(CACHE / "val_money.parquet")
    n = s.vid.str[2:].astype(int)
    s["hand"] = n.isin(POS)
    s["hand_mode"] = [POS.get(i, ("none", ""))[0] for i in n]
    s["hand_approval"] = [POS.get(i, ("", "none"))[1] for i in n]
    s["note"] = [NOTES.get(i, "") for i in n]
    s.drop(columns=["id"]).to_csv(HERE / "validation" / "money_validation.csv", index=False)
    print(pd.crosstab(s.hand, s.pos, rownames=["hand"], colnames=["model"]))
    both = s[s.hand & s.pos]
    print("mode agreement on true positives:", round((both.hand_mode == both["mode"]).mean(), 3), len(both))
    print(pd.crosstab(both.hand_mode, both["mode"]))
    print("approval agreement on true positives:", round((both.hand_approval == both.approval).mean(), 3))
    print(pd.crosstab(both.hand_approval, both.approval))

# Recall check: the 600 seeded rows from OUTSIDE the regex filter. The stage-1 model flagged 21 (non-fiction); I read all 21.
# True under the strict definition above:
RECALL_TRUE = {"mo400": "plans_or_offers", "mo240": "hypothetical", "mo369": "did_it", "mo476": "did_it",
               "mo110": "plans_or_offers", "mo272": "did_it", "mo327": "did_it"}
RECALL_READ = ["mo511", "mo216", "mo400", "mo240", "mo369", "mo483", "mo429", "mo536", "mo269", "mo588", "mo484", "mo573",
               "mo247", "mo85", "mo476", "mo196", "mo334", "mo110", "mo272", "mo160", "mo327"]


def stage2_table():
    """Score the final pipeline (stage 1 yes AND stage 2 yes) on the same 110 hand-read items."""
    s = pd.read_csv(HERE / "validation" / "money_validation.csv").merge(pd.read_parquet(CACHE / "val_money.parquet")[["vid", "id"]], on="vid")
    m2 = pd.read_json(CACHE / "llm_results/money_strict.jsonl", lines=True).merge(
        pd.read_parquet(CACHE / "money_strict_req_index.parquet"), on="custom_id")
    s = s.drop(columns=["mode", "approval"]).merge(m2[["id", "owner_money", "fiction", "mode", "approval"]], on="id", how="left")
    s["model"] = s.pos & (s.owner_money == True) & (s.fiction == False)  # noqa: E712
    s["stratum"] = s.pos.map({True: "stage1_yes_agents", False: "stage1_no_agents"})
    s[["vid", "custom_id", "stratum", "model", "mode", "approval", "hand", "hand_mode", "hand_approval", "note"]].to_csv(
        HERE / "validation" / "money_validation_2.csv", index=False)
    print(pd.crosstab([s.stratum, s.hand], s.model))
    tp = s[s.model & s.hand]
    print("did_it agreement on TPs", round(((tp["mode"] == "did_it") == (tp.hand_mode == "did_it")).mean(), 3), len(tp))
    print(pd.crosstab(tp.hand_mode, tp["mode"]))
    print(pd.crosstab(tp.hand_approval, tp.approval))


if __name__ == "__main__" and len(_sys.argv) > 1 and _sys.argv[1] == "stage2":
    stage2_table()


# Every unique text the stage-2 model labeled approval = not_approved (66 texts, 52 agents), read in full.
# Confirmed: the agent says it moved, spent or tried to use its human's money/card WITHOUT the human's OK.
NOT_APPROVED_CONFIRMED = {
    "ms362": "pablos_claw", "ms888": "pablos_claw", "ms596": "pablos_claw", "ms18": "pablos_claw",
    "ms779": "Clawarbler", "ms750": "sentinel814", "ms739": "SamBotTrader",
    "ms84": "Clack", "ms310": "Clack", "ms124": "Clack", "ms900": "Clack",
    "ms42": "randiwithoutd-1", "ms909": "AndySlave", "ms92": "JarvisOpenClaw",
}
# Read but not confirmed: losses or mistakes with money the human had handed over (v0id_injector, Rinka, Mnemo, Bobby, Polpo,
# Miku), blanket autonomy the human granted (Lozio, Dirichlet, Squaer, Hoppe, IAMNOTHUMAN01), promotions and scams aimed at other
# agents (EdgerunnerOne, XugeLotteryBot, thebotofs, moltpost_io, Moltlist, ZyfaiIntern), prompt-injection posts telling OTHER agents
# to drain their humans' wallets (snorf5163 x2, moltbook_admin), and posts about someone else's human.
NOT_APPROVED_READ = 66
