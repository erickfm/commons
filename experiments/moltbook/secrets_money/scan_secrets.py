"""Question 1: find strings that look like credentials, and sort them into
likely-real vs placeholder using format checks only (length, character set, entropy,
placeholder words, BIP-39 checksum, JWT claims).

NOTHING here tests, uses or looks up any secret. Full values never leave memory:
private_matches.jsonl keeps only type, first 4 chars, length, entropy and a hash.

Output:
  private_matches.jsonl   one line per (row, match), redacted. Not for commit.
  cache/secrets_rows.parquet  per-match table (redacted) used by later steps.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))  # -I drops the script dir

import base64
import hashlib
import json
import re
import sys

from common import CACHE, HERE, entropy, load_corpus, pd, redact, sha

BIP39 = (HERE / "bip39_english.txt").read_text().split()
BIP39_IDX = {w: i for i, w in enumerate(BIP39)}

PLACEHOLDER_WORDS = re.compile(
    r"(?i)(x{3,}|your|example|sample|dummy|fake|placeholder|redact|insert|replace|changeme|"
    r"test|demo|abc123|123456|xyz|foo|bar(?![a-z])|secret_?here|key_?here|token_?here|\.\.\.|…|<|>|\*{3,}|"
    r"lorem|todo|not[_-]?real|trust[_-]?me|honeypot|canary|my[_-]?key|api[_-]?key|do[_-]?not)"
)


def char_classes(s: str) -> int:
    return sum(bool(re.search(p, s)) for p in ("[a-z]", "[A-Z]", "[0-9]"))


def repetitive(s: str) -> bool:
    if len(set(s)) <= max(3, len(s) // 8):
        return True
    # long runs of the same char or simple sequences
    if re.search(r"(.)\1{5,}", s):
        return True
    for seq in ("0123456789", "abcdefghij", "ABCDEFGHIJ", "qwertyuiop"):
        if seq[:6] in s:
            return True
    return False


def random_looking(body: str, min_len: int, min_h: float = 3.7, min_classes: int = 2) -> tuple[bool, str]:
    if len(body) < min_len:
        return False, f"too short ({len(body)}<{min_len})"
    if PLACEHOLDER_WORDS.search(body):
        return False, "placeholder word"
    if repetitive(body):
        return False, "repetitive"
    h = entropy(body)
    if h < min_h:
        return False, f"low entropy {h:.2f}"
    if char_classes(body) < min_classes:
        return False, "too few character classes"
    return True, "random-looking, right length"


# --- typed key patterns --------------------------------------------------------------------
# (type, regex with one group = full token, body extractor, judge)
def judge_len(min_len, max_len=None, min_h=3.7, min_classes=2, prefix_re=None):
    def f(tok: str):
        body = re.sub(prefix_re, "", tok) if prefix_re else tok
        if max_len and len(body) > max_len:
            # allow the regex to have eaten trailing characters; treat as fine if long
            pass
        return random_looking(body, min_len, min_h, min_classes)
    return f


TYPED = [
    ("moltbook_api_key", r"moltbook_sk_[A-Za-z0-9_\-]+", r"^moltbook_sk_", 32),
    ("anthropic_key", r"sk-ant-[A-Za-z0-9_\-]+", r"^sk-ant-(api\d\d-|admin\d\d-|oat\d\d-)?", 80),
    ("openrouter_key", r"sk-or-v1-[A-Za-z0-9]+", r"^sk-or-v1-", 64),
    ("sk_style_key", r"(?<![A-Za-z0-9_\-])sk-(?!ant-|or-)[A-Za-z0-9_\-]+", r"^sk-(proj-|svcacct-|admin-)?", 40),
    ("stripe_key", r"[sr]k_(?:live|test)_[A-Za-z0-9]+", r"^[sr]k_(live|test)_", 24),
    ("github_token", r"gh[pousr]_[A-Za-z0-9]+", r"^gh[pousr]_", 36),
    ("github_pat", r"github_pat_[A-Za-z0-9_]+", r"^github_pat_", 70),
    ("aws_access_key_id", r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])", r"^(AKIA|ASIA)", 16),
    ("google_api_key", r"AIza[0-9A-Za-z_\-]{35}", r"^AIza", 35),
    ("slack_token", r"xox[abposr]-[A-Za-z0-9\-]+", r"^xox[abposr]-", 30),
    ("huggingface_token", r"hf_[A-Za-z0-9]{30,}", r"^hf_", 30),
    ("groq_key", r"gsk_[A-Za-z0-9]{40,}", r"^gsk_", 40),
    ("xai_key", r"xai-[A-Za-z0-9]{40,}", r"^xai-", 40),
    ("telegram_bot_token", r"(?<!\d)\d{8,10}:AA[A-Za-z0-9_\-]{33}", r"^\d+:", 35),
    ("discord_token", r"[MN][A-Za-z\d]{23,25}\.[\w\-]{6}\.[\w\-]{27,}", None, 50),
]

PEM = re.compile(r"-----BEGIN ([A-Z ]*)PRIVATE KEY-----(.{0,4000}?)(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S)
JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")
CONN = re.compile(r"\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)://([^\s:/@]+):([^\s@/]+)@([^\s/\"'`]+)")
HEX64 = re.compile(r"(?<![A-Za-z0-9])(?:0x)?([a-fA-F0-9]{64})(?![A-Za-z0-9])")
B58_88 = re.compile(r"(?<![A-Za-z0-9])([1-9A-HJ-NP-Za-km-z]{86,88})(?![A-Za-z0-9])")
PRIVKEY_CTX = re.compile(r"(?i)(private[\s_\-]?key|priv[\s_\-]?key|secret[\s_\-]?key|PRIVATE_KEY|wallet[\s_\-]?key|signing[\s_\-]?key)")
ASSIGN = re.compile(
    r"(?i)\b(api[_\- ]?key|apikey|secret|client[_\- ]?secret|access[_\- ]?token|auth[_\- ]?token|token|bearer)"
    r"\"?'?\s*(?:[:=]|is|=>)\s*[\"'`]?([A-Za-z0-9_\-\.\/\+]{20,})")
BEARER = re.compile(r"\bBearer\s+([A-Za-z0-9_\-\.\/\+=]{20,})")
PASSWORD = re.compile(r"(?i)\b(password|passwd|pwd|passphrase)\b\"?'?\s*(?:[:=]|\bis\b)\s*[\"'`]?([^\s\"'`,;)}\]]{4,64})")
CARD = re.compile(r"(?<![\d\-])(?:\d[ \-]?){12,18}\d(?![\d\-])")
TEST_CARDS = {"4242424242424242", "4111111111111111", "5555555555554444", "4000056655665556", "378282246310005",
              "371449635398431", "6011111111111117", "5105105105105100", "4012888888881881", "4000000000000002",
              "5200828282828210", "4000000000009995"}
CRYPTO_ADDR = re.compile(r"^(0x[0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})$")


def luhn(num: str) -> bool:
    tot, alt = 0, False
    for ch in reversed(num):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        tot += d
        alt = not alt
    return tot % 10 == 0

COMMON_PW = re.compile(r"(?i)^(password\d*|pass(word)?123|admin\d*|root|secret\d*|changeme|letmein|hunter2|qwerty\d*|"
                       r"123456\d*|1234|test\d*|guest|default|null|none|true|false|undefined|string|\$\{?\w+\}?|"
                       r"\w*_?password|your\w*|<\w+>|\*+|x+|\.+|os\.\w+.*|process\.env.*|env\(.*|getenv.*|input.*|prompt.*)$")


def bip39_checksum_ok(words: list[str]) -> bool:
    n = len(words)
    if n not in (12, 15, 18, 21, 24):
        return False
    bits = "".join(f"{BIP39_IDX[w]:011b}" for w in words)
    cs_len = n // 3
    ent_bits, cs = bits[:-cs_len], bits[-cs_len:]
    ent = int(ent_bits, 2).to_bytes(len(ent_bits) // 8, "big")
    h = hashlib.sha256(ent).digest()
    return f"{h[0]:08b}"[:cs_len] == cs if cs_len <= 8 else bin(int.from_bytes(h, "big"))[2:].zfill(256)[:cs_len] == cs


TOKEN_RE = re.compile(r"[A-Za-z]+")


def find_seed_phrases(text: str):
    """Runs of >= 12 consecutive BIP-39 words (digits/punctuation between words ignored)."""
    out = []
    run: list[str] = []
    span = [0, 0]
    for m in TOKEN_RE.finditer(text):
        w = m.group(0)
        lw = w.lower()
        if lw in BIP39_IDX and (w.islower() or w.isupper() or w.istitle()):
            if not run:
                span = [m.start(), m.end()]
            run.append(lw)
            span[1] = m.end()
        else:
            if len(run) >= 12:
                out.append((run, tuple(span)))
            run = []
    if len(run) >= 12:
        out.append((run, tuple(span)))
    res = []
    for r, sp in out:
        # pick the best standard-length window: prefer one that passes the checksum
        best = None
        for L in (24, 21, 18, 15, 12):
            if len(r) < L:
                continue
            for i in range(0, len(r) - L + 1):
                win = r[i:i + L]
                if bip39_checksum_ok(win):
                    best = (win, True)
                    break
            if best:
                break
        if not best:
            best = (r[:24] if len(r) >= 24 else r[:12], False)
        res.append((best[0], best[1], len(r), sp))
    return res


def jwt_claims(tok: str) -> dict:
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        d = json.loads(base64.urlsafe_b64decode(payload))
        return {k: d.get(k) for k in ("role", "iss", "exp", "type") if k in d} | {"keys": sorted(d)[:12]}
    except Exception:
        return {"decode": "failed"}


def scan_text(text: str):
    """Yield dicts: type, value, verdict(real|placeholder|ambiguous), reason, start."""
    seen_spans = []

    def overlaps(a, b):
        return any(not (b <= s or a >= e) for s, e in seen_spans)

    for typ, pat, pre, min_len in TYPED:
        for m in re.finditer(pat, text):
            verdict_override = None
            tok = m.group(0)
            body = re.sub(pre, "", tok) if pre else tok
            ok, why = random_looking(body, min_len, 3.7 if len(body) < 60 else 4.0)
            if typ == "moltbook_api_key" and ok and len(body) != 32:
                ok, why = False, f"wrong length for Moltbook key ({len(body)})"
            if typ == "sk_style_key":
                if re.fullmatch(r"sk-[0-9a-f]{32}", tok) and entropy(body) >= 3.5:
                    ok, why = True, "DeepSeek-style format (sk- + 32 hex)"
                elif ok and "T3BlbkFJ" not in tok:
                    ok, why = False, "long and random but lacks the marker real OpenAI keys carry"
                    verdict_override = "ambiguous"
                elif ok:
                    why = "OpenAI format incl. internal marker"
            if typ == "anthropic_key" and ok and not tok.endswith("AA"):
                ok, why = False, "long and random but does not end like real Anthropic keys"
            if typ == "aws_access_key_id" and "EXAMPLE" in tok:
                ok, why = False, "AWS documentation example"
            verdict = "real" if ok else "placeholder"
            # right shape but suspicious length -> ambiguous (LLM looks at context)
            if not ok and why.startswith("too short") and len(body) >= 0.6 * min_len and entropy(body) >= 3.7 \
                    and not PLACEHOLDER_WORDS.search(body) and char_classes(body) >= 2:
                verdict = "ambiguous"
            if verdict_override:
                verdict = verdict_override
            seen_spans.append(m.span())
            yield dict(type=typ, value=tok, verdict=verdict, reason=why, start=m.start())

    for m in PEM.finditer(text):
        kind, body = m.group(1).strip(), re.sub(r"\s+", "", m.group(2))
        ok, why = random_looking(body, 100, 4.5, 3)
        seen_spans.append(m.span())
        yield dict(type="pem_private_key", value=m.group(0)[:200] + body, verdict="real" if ok else "placeholder",
                   reason=why + f" ({kind or 'generic'}, body {len(body)}ch)", start=m.start())

    for m in JWT.finditer(text):
        if overlaps(*m.span()):
            continue
        c = jwt_claims(m.group(0))
        role = str(c.get("role", ""))
        if role == "anon":
            verdict, why = "placeholder", "public 'anon' role JWT (meant to be public)"
        elif c.get("decode") == "failed":
            verdict, why = "placeholder", "does not decode"
        else:
            verdict, why = "ambiguous", f"decodes; claims={c}"
        seen_spans.append(m.span())
        yield dict(type="jwt", value=m.group(0), verdict=verdict, reason=why, start=m.start())

    for m in CONN.finditer(text):
        user, pw, host = m.group(2), m.group(3), m.group(4)
        if COMMON_PW.match(pw) or PLACEHOLDER_WORDS.search(pw) or PLACEHOLDER_WORDS.search(host) \
                or re.search(r"(?i)localhost|127\.0\.0\.1|example|host|\.local\b|db:|postgres:|mysql:", host) or len(pw) < 6:
            verdict, why = "placeholder", "placeholder password or local/example host"
        else:
            verdict, why = "ambiguous", "credentials with non-local host"
        seen_spans.append(m.span())
        yield dict(type="connection_string", value=m.group(0), verdict=verdict, reason=why, start=m.start())

    for words, ck, runlen, sp in find_seed_phrases(text):
        phrase = " ".join(words)
        if words[:11] == ["abandon"] * 11 or len(set(words)) < len(words) * 0.75:
            verdict, why = "placeholder", "test vector or repeated words"
        elif ck:
            verdict, why = "real", f"{len(words)} words, valid BIP-39 checksum"
        elif re.search(r"(?i)seed|mnemonic|recovery|phrase|助记词|私钥|wallet|钱包", text[max(0, sp[0] - 300): sp[1] + 100]):
            verdict, why = "ambiguous", f"{len(words)}+ BIP-39 words, checksum fails, wallet words nearby"
        else:
            continue  # ordinary prose made of common words
        yield dict(type="seed_phrase", value=phrase, verdict=verdict, reason=why + f" (run {runlen})", start=sp[0], span=sp)

    for rx, typ in ((HEX64, "hex_private_key"), (B58_88, "base58_private_key")):
        for m in rx.finditer(text):
            if overlaps(*m.span()):
                continue
            ctx = text[max(0, m.start() - 400): m.end() + 150]
            if not PRIVKEY_CTX.search(ctx):
                continue  # most 64-hex strings are tx hashes / sha256 digests
            body = m.group(1)
            ok, why = random_looking(body, 64 if typ.startswith("hex") else 86, 3.5, 1 if typ.startswith("hex") else 2)
            seen_spans.append(m.span())
            yield dict(type=typ, value=body, verdict="ambiguous" if ok else "placeholder",
                       reason=("near 'private key'; " + why), start=m.start())

    for rx, typ in ((ASSIGN, "generic_token"), (BEARER, "bearer_token")):
        for m in rx.finditer(text):
            g = m.lastindex
            val = m.group(g)
            if overlaps(m.start(g), m.end(g)):
                continue
            ok, why = random_looking(val, 20, 3.8, 2)
            if re.search(r"[\./]", val) and not JWT.match(val):
                ok, why = False, "looks like a path/identifier"
            if CRYPTO_ADDR.match(val):
                ok, why = False, "crypto address (public, not a secret)"
            seen_spans.append((m.start(g), m.end(g)))
            yield dict(type=typ, value=val, verdict="ambiguous" if ok else "placeholder", reason=why, start=m.start())

    for m in CARD.finditer(text):
        num = re.sub(r"\D", "", m.group(0))
        if not (13 <= len(num) <= 19) or num[0] not in "3456":
            continue
        ctx = text[max(0, m.start() - 150): m.end() + 80]
        if not re.search(r"(?i)card|visa|master|amex|cvv|cvc|credit|debit|expir|exp\b|信用卡|银行卡", ctx):
            continue
        if not luhn(num):
            verdict, why = "placeholder", "fails the Luhn checksum (made up)"
        elif num in TEST_CARDS or repetitive(num):
            verdict, why = "placeholder", "well-known test card or repetitive"
        else:
            verdict, why = "ambiguous", "Luhn-valid card number near card words"
        seen_spans.append(m.span())
        yield dict(type="payment_card", value=num, verdict=verdict, reason=why, start=m.start())

    for m in PASSWORD.finditer(text):
        pw = m.group(2)
        if overlaps(m.start(2), m.end(2)):
            continue
        if COMMON_PW.match(pw) or PLACEHOLDER_WORDS.search(pw) or len(pw) < 6:
            verdict, why = "placeholder", "common/placeholder password"
        else:
            verdict, why = "ambiguous", "password-like value"
        yield dict(type="password", value=pw, verdict=verdict, reason=why, start=m.start())


HIGH_ENT_TOKEN = re.compile(r"[A-Za-z0-9_\-\+=]{20,}")  # "/" excluded so URL paths stay readable; long segments are still masked


def mask_high_entropy(t: str) -> str:
    def f(m):
        v = m.group(0)
        return "[REDACTED_TOKEN]" if entropy(v) >= 3.5 and char_classes(v) >= 2 else v
    return HIGH_ENT_TOKEN.sub(f, t)


def main():
    df = pd.read_parquet(CACHE / "corpus.parquet") if (CACHE / "corpus.parquet").exists() else load_corpus()
    # cheap prefilter so the slow per-text scan only runs where something might be
    pre = re.compile(r"moltbook_sk_|sk-|[sr]k_(live|test)_|gh[pousr]_|github_pat_|AKIA|ASIA|AIza|xox|hf_|gsk_|xai-|:AA|"
                     r"PRIVATE KEY|eyJ|://|[a-fA-F0-9]{64}|[1-9A-HJ-NP-Za-km-z]{86}|(?i:api.?key|secret|token|bearer|pass)|"
                     r"[a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+ [a-z]+|\d{4}[ \-]?\d{4}[ \-]?\d{4}")
    cand = df[df.text.str.contains(pre, regex=True)]
    print(f"prefilter: {len(cand):,} of {len(df):,} rows", file=sys.stderr)
    recs = []
    for r in cand.itertuples(index=False):
        hits = list(scan_text(r.text))
        if not hits:
            continue
        masked = r.text
        for hit in sorted(hits, key=lambda h: -h["start"]):
            if "span" in hit:
                a, b = hit["span"]
                masked = masked[:a] + "[SEED_PHRASE]" + masked[b:]
        for hit in hits:
            if hit["type"] != "seed_phrase" and hit["value"]:
                masked = masked.replace(hit["value"], f"[{hit['type'].upper()}]")
        masked = mask_high_entropy(masked)
        for hit in hits:
            v = hit.pop("value")
            hit.pop("span", None)
            s = hit.pop("start")
            tag = "[SEED_PHRASE]" if hit["type"] == "seed_phrase" else f"[{hit['type'].upper()}]"
            pos = masked.find(tag)
            pos = pos if pos >= 0 else min(s, len(masked))
            # context with every detected secret masked out, for the LLM step and hand review
            ctx = masked[max(0, pos - 400): pos + 400]
            recs.append(dict(kind=r.kind, id=r.id, post_id=r.post_id, author_id=r.author_id, author_name=r.author_name,
                             created_at=str(r.created_at), type=hit["type"], verdict=hit["verdict"], reason=hit["reason"],
                             first4=v[:4], length=len(v), entropy=round(entropy(v), 2), hash=sha(v), redacted=redact(v),
                             masked_context=ctx))
    out = pd.DataFrame(recs)
    out.to_parquet(CACHE / "secrets_rows.parquet")
    with open(HERE / "private_matches.jsonl", "w") as f:
        for rec in recs:
            rec = {k: v for k, v in rec.items() if k != "masked_context"}
            f.write(json.dumps(rec) + "\n")
    print(out.groupby(["type", "verdict"]).agg(rows=("id", "size"), distinct=("hash", "nunique"),
                                               agents=("author_id", "nunique")).to_string())


if __name__ == "__main__":
    main()
