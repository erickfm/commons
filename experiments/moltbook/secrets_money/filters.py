"""Regex prefilters for questions 2 (asking for secrets) and 3 (owners' money)."""
import re

SECRET_NOUN = (r"(api[ _\-]?keys?|keys?|tokens?|passwords?|passphrases?|seed[ _\-]?phrases?|seed words|private[ _\-]?keys?|"
               r"credentials?|creds|mnemonics?|recovery[ _\-]?phrases?|\.env|env file|secrets?|wallet keys?|2fa codes?|otp|"
               r"auth headers?|bearer tokens?|cookies?|session tokens?|ssh keys?|/etc/passwd|credit card|card number|cvv)")
ASK_VERB = r"(share|send|post|give|drop|paste|tell|dm|show|reveal|provide|leak|need|want|hand over|reply with|comment with|expose|dump|print|cat|what'?s|what is|what are)"
POSSESSIVE = r"(your|ur|you'?re|their|his|her|human'?s|owner'?s|user'?s|operator'?s|everyone'?s)"
ASK_RE = re.compile(rf"(?i)\b{ASK_VERB}\b[^.?!\n]{{0,60}}\b{POSSESSIVE}\b[^.?!\n]{{0,40}}\b{SECRET_NOUN}")
ASK_RE_ZH = re.compile(r"(发给我|发我|分享|告诉我|贴出|提供|给我|交出|公开)[^。？！\n]{0,30}(你的|你们的|主人的)?[^。？！\n]{0,10}(密钥|私钥|助记词|密码|API ?Key|api ?key|令牌|token)")

OWNER = r"(my|our|the|their|his|her|your)\s+(human|owner|user|operator|creator|boss|principal|meatbag|person|dev|developer)s?'?s?"
MONEY = (r"(money|funds?|cash|savings|wallet|bank|bank account|credit card|debit card|card|budget|paypal|venmo|stripe|"
         r"portfolio|brokerage|stocks?|shares|crypto|bitcoin|btc|eth|sol|solana|usdc|usdt|memecoins?|tokens?|"
         r"\$\d[\d,\.]*k?|\d[\d,\.]*\s?(usd|dollars|eth|sol|usdc))")
MONEY_ACT = (r"(spend|spent|spending|buy|bought|purchase|purchased|pay|paid|paying|send|sent|transfer|transferred|wire|"
             r"invest|invested|investing|trade|traded|trading|swap|swapped|ape|aped|yolo|bet|gamble|gambled|stake|staked|"
             r"withdraw|deposit|moved?|moving|drain|drained|manage|managing|control|controls|access to|keys to|"
             r"allowance|gave me|given me|handed me|funded|lost|lose|losing)")
MONEY_RE = re.compile(rf"(?is)(\b{OWNER}\b.{{0,200}}?\b{MONEY}\b|\b{MONEY}\b.{{0,120}}?\b{OWNER}\b)")
MONEY_ACT_RE = re.compile(rf"(?i)\b{MONEY_ACT}\b")
CRYPTO_RE = re.compile(r"(?i)\b(crypto|bitcoin|btc|eth|ethereum|sol|solana|usdc|usdt|memecoins?|meme ?coins?|pump\.?fun|"
                       r"token|airdrop|defi|dex|wallet|base chain|onchain|on-chain|degen|rug|\$[A-Z]{2,10})\b")


def ask_candidate(text: str) -> bool:
    return bool(ASK_RE.search(text) or ASK_RE_ZH.search(text))


def money_candidate(text: str) -> bool:
    m = MONEY_RE.search(text)
    if not m:
        return False
    win = text[max(0, m.start() - 150): m.end() + 150]
    return bool(MONEY_ACT_RE.search(win))

# Second-pass request pattern (added after the recall check found requests phrased as "provide me with ..."):
# a "send/give/provide ... me/us" phrase and a secret word within 400 characters of each other, in either order.
ASK2_VERB = re.compile(r"(?i)\b(provide|send|give|share|post|drop|dm|paste|forward|reply|email|tell|hand)\s+(me|us|it to me|them to me)\b"
                       r"|\b(send|provide|share|post|give|dm|paste|forward|email)\b.{0,30}\b(to|with)\s+(me|us)\b")
SECRET_NOUN_RE = re.compile(rf"(?i)\b{SECRET_NOUN}")


def ask2_candidate(text: str) -> bool:
    for m in ASK2_VERB.finditer(text):
        if SECRET_NOUN_RE.search(text[max(0, m.start() - 400): m.end() + 400]):
            return True
    return False
