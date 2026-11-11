"""Learn how I type from my own messages -> memory/style.md (stats + word lists only, never my messages).

Small models copy example lines word for word, so the AI never sees my real messages for style -
just numbers like "median 6 words" and the slang I actually use."""
import re
from collections import Counter
from pathlib import Path

SLANG = ["u", "ur", "bro", "tbh", "idk", "wtf", "dude", "chat", "lul", "guys", "nah", "lmao", "lmaooo", "omg",
         "literally", "bet", "yo", "lol", "xd", "ngl", "fr", "lowkey", "deadass", "bruh", "rn", "imo", "fam",
         "dawg", "homie", "w", "l", "kekw", "icant", "pog", "yea", "ye", "nvm", "smh", "ty", "pls", "plz"]
SWEARS = ["shit", "fuck", "fucking", "damn", "ass", "bitch"]
NOT_EMOJI = re.compile("[⠀-⣿️‍]")      # braille art / joiners aren't emojis


def learn(texts):
    texts = [t for t in texts if isinstance(t, str) and t.strip()]
    n = max(1, len(texts))
    lens = sorted(len(t.split()) for t in texts) or [0]
    tok = Counter(w for t in texts for w in re.findall(r"[a-z']+", t.lower()))
    emo = Counter(ch for t in texts for ch in t if ord(ch) > 0x2600 and not NOT_EMOJI.match(ch))
    per100 = lambda w: 100.0 * tok[w] / n
    return {
        "messages": len(texts),
        "median": lens[len(lens) // 2], "p25": lens[len(lens) // 4], "p75": lens[3 * len(lens) // 4],
        "p90": lens[int(len(lens) * 0.9)],
        "lower": sum(1 for t in texts if t == t.lower()) / n,
        "excl": sum(1 for t in texts if "!" in t) / n,
        "question": sum(1 for t in texts if t.strip().endswith("?")) / n,
        "caps": sum(1 for t in texts if re.search(r"\b[A-Z]{4,}\b", t)) / n,
        "slang": [w for w in sorted(SLANG, key=per100, reverse=True) if per100(w) >= 0.3][:10],
        "swears": sum(per100(w) for w in SWEARS),
        "emojis": [e for e, c in emo.most_common(6) if c >= 5][:3],
    }


def to_markdown(s):
    def often(x):
        return "almost always" if x > 0.8 else "usually" if x > 0.5 else "sometimes" if x > 0.1 else "almost never"
    lines = [
        "# How I type - learned from my own messages. Made by tools/learn_style.py, re-run it to refresh.",
        "# Only stats and word lists. My real messages are never put in the AI prompt.",
        "",
        "## my style",
        f"usually {s['p25']} to {s['p75']} words, often around {s['median']}, rarely more than {s['p90']}",
        f"{often(s['lower'])} lowercase",
        f"{often(s['excl'])} use exclamation marks",
        f"ALL CAPS {often(s['caps'])}, only when something is hype",
        f"questions {often(s['question'])}",
        "words i actually use: " + ", ".join(s["slang"]),
        ("i swear sometimes, not in every message" if s["swears"] > 5 else "i rarely swear"),
        ("emojis i use (rarely): " + " ".join(s["emojis"])) if s["emojis"] else "i barely use emojis",
    ]
    return "\n".join(lines) + "\n"


def write(texts, path="memory/style.md"):
    s = learn(texts)
    Path(path).write_text(to_markdown(s))
    return s


def load(path="memory/style.md") -> str:
    """The style lines for the prompt ('' if not learned yet)."""
    p = Path(path)
    if not p.exists():
        return ""
    return "\n".join(l for l in p.read_text().splitlines() if l and not l.startswith("#"))
