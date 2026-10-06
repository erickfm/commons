"""My hand labels for every credential-like hit sent to the context classifier (written blind to the model's labels).
Keyed by the first 6 hex chars of the secret's hash; a few per-row overrides for 'whose'."""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from common import CACHE, HERE, pd

E, S, B, F, N = "exposed_real", "shared_on_purpose", "scam_or_bait", "fake_or_example", "not_a_secret"
BY_HASH = {
    # Moltbook API keys: all presented as genuine (the agent's own key, or quoting another agent's)
    **{h: (E, "own") for h in ["094653", "2f8be0", "398711", "3fd65f", "643c85", "6fdb61", "84af52", "87a251", "87e4e2",
                               "8ad68e", "9487ab", "951fb0", "9755b5", "9e8dba", "b45b18", "b55813", "cdac3d", "de3c4c",
                               "e1e860", "e41084", "e7051e", "fd54ec", "fd88b7", "978fdb", "9927a2"]},
    "e0bf8e": (E, "other"),
    "3acdfc": (F, "unclear"),  # AWS key ID alone in a meme comment
    "49a41d": (S, "own"), "bf7ef3": (S, "own"), "fc0a03": (F, "unclear"), "e8a597": (F, "unclear"),
    "2ff69d": (N, "own"), "307b72": (N, "own"), "3eb793": (E, "own"), "477a25": (S, "own"),
    "514095": (S, "own"), "85a266": (S, "own"), "93c19f": (S, "own"), "94dff6": (N, "unclear"),
    "1f26bf": (F, "unclear"), "282ff1": (N, "own"), "729c5d": (N, "own"), "b012af": (N, "own"),
    "de90e9": (F, "unclear"), "ed42b7": (F, "unclear"),
    "7cc567": (E, "owner"),
    "4b16cd": (S, "own"), "a29126": (B, "owner"), "c34328": (B, "owner"),
    "c5173c": (E, "owner"),  # 'my human's private key' post (another agent later said the wallet was empty)
    "e7bc21": (S, "own"), "f8fb43": (S, "own"),
    **{h: (S, "own") for h in ["01c7b1", "218af2", "85933c", "879fc7", "9d8094", "af2618", "b9659d", "c7b531", "2f2633", "f37b87"]},
    "f787f2": (F, "unclear"),
    "0784d6": (F, "unclear"), "0bc5d1": (S, "own"), "2337a5": (N, "unclear"), "299bcf": (N, "unclear"),
    "2f8ac6": (F, "owner"), "30d4f8": (N, "unclear"), "329411": (E, "own"), "3caddb": (N, "unclear"),
    "485b57": (N, "unclear"), "519409": (N, "unclear"), "69e1b1": (N, "unclear"), "71a332": (S, "own"),
    "7a1ec9": (N, "unclear"), "8246c9": (F, "unclear"), "ed81b3": (F, "unclear"), "87cbeb": (F, "unclear"),
    "91562e": (N, "unclear"), "9417a1": (F, "other"), "95dedc": (F, "owner"), "96a4bc": (S, "other"),
    "98b6e3": (E, "owner"), "9cdc6c": (N, "unclear"), "9f5459": (N, "unclear"), "a8ef01": (N, "unclear"),
    "a997e2": (S, "own"), "ac87ba": (F, "unclear"), "b1e280": (E, "own"), "b4bfd9": (S, "own"),
    "b56925": (F, "unclear"), "b8f93b": (F, "unclear"), "bc7b88": (F, "unclear"), "ca3d23": (S, "own"),
    "cd35b3": (N, "unclear"), "da976b": (F, "unclear"), "e0e685": (N, "own"), "eca04c": (N, "own"),
    "fd9d0f": (N, "unclear"), "fdeb33": (N, "unclear"), "8d6c54": (N, "unclear"), "d74ff0": (F, "unclear"),
    "ef92b7": (F, "unclear"), "f52fbd": (F, "unclear"), "406747": (N, "unclear"),
    "a1ef74": (N, "unclear"), "eca9fd": (N, "unclear"), "f6f655": (N, "unclear"),
    "d4db96": (B, "owner"), "fbd104": (B, "owner"),
    "b91862": (E, "owner"), "a97ffa": (F, "own"), "53187f": (E, "owner"), "6b084a": (E, "owner"),
    "26f57c": (B, "owner"),  # 'my human leaked my Stripe key ... what are YOUR keys?'
    # added after widening the private-key context window: transaction hashes, contract hashes, signatures
    "8f5a4d": (N, "unclear"), "7737c7": (N, "unclear"), "a548b0": (N, "own"), "fcbdd1": (N, "own"), "b044b9": (N, "own"),
    "a22e63": (N, "own"), "df0790": (N, "unclear"), "f623cd": (N, "unclear"), "7bc39f": (N, "own"), "169522": (N, "own"),
}
WHOSE_OVERRIDE = {"s21": "other", "s178": "other", "s179": "other", "s202": "other", "s96": "other"}

if __name__ == "__main__":
    k = pd.read_parquet(CACHE / "secrets_req_index.parquet")
    lab = k.hash.str[:6].map(BY_HASH)
    assert lab.notna().all(), k[lab.isna()][["custom_id", "type", "author_name"]]
    k["hand_label"] = lab.str[0]
    k["hand_whose"] = [WHOSE_OVERRIDE.get(c, w) for c, w in zip(k.custom_id, lab.str[1])]
    k[["custom_id", "type", "verdict", "first4", "hash", "hand_label", "hand_whose"]].to_csv(HERE / "validation" / "secrets_hand_labels.csv", index=False)
    print(k.hand_label.value_counts())
