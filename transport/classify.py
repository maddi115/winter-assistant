"""Step 1 - coarse level: what kind of question is this? (pure rules)"""
import re

YES_NO_START = ("do ", "does ", "did ", "is ", "are ", "am ", "can ", "could ", "would ",
                "will ", "have ", "has ", "should ", "r u ", "u ", "you ", "ever ")
LIST_HINTS = ("what are ", "which ", "list ", "name some", "what kind", "what kinds", "what type",
              "what games", "what foods", "what music", "what shows", "what movies")
SLANG = r"\b(lol|lmao|lmfao|yo|bro|bruh|fr|tbh|ngl|dude|fam|u|ur|ya|rn|idk|deadass)\b"
FOLLOWUPS = ("anything else", "what else", "tell me more", "more", "go on", "and", "keep going",
             "any more", "anymore", "what else u got", "say more")
WH = ("what", "where", "who", "when", "why", "how", "which")


def norm(text: str) -> str:
    t = text.lower().replace("’", "'").replace("'", "")
    t = re.sub(r"[^\w\s?]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def question_type(q: str) -> str:
    t = norm(q).rstrip("?").strip() + " "
    if t.startswith(("when ", "what time", "how long ago", "what day", "what year")):
        return "temporal"
    if t.startswith("where "):
        return "location"
    if t.startswith(LIST_HINTS):
        return "list"
    if t.startswith(YES_NO_START):
        return "yes_no"
    return "factual"


def is_question(q: str) -> bool:
    t = norm(q)
    return t.endswith("?") or t.startswith(WH) or question_type(q) == "yes_no"


def about_me(q: str, persona: str, handles) -> bool:
    """Is the visitor asking about the owner? ('do you...', 'your...', or by name)"""
    t = norm(q)
    if re.search(r"\b(you|your|yours|yourself|u|ur|ya)\b", t):
        return True
    names = [persona.lower()] + [h.lower() for h in handles]
    return any(re.search(rf"\b{re.escape(n)}\b", t) for n in names if n)


def is_followup(q: str) -> bool:
    t = norm(q).rstrip("?").strip()
    return t in FOLLOWUPS or t.startswith(("anything else", "what else"))


def tone(q: str) -> str:
    if re.search(SLANG, q.lower()) or not re.search(r"[A-Z]", q):
        return "casual"
    return "neutral"


def asks_negative(q: str) -> bool:
    """'do you hate X?' flips what YES means."""
    return bool(re.search(r"\b(hate|dislike|cant stand|cannot stand)\b", norm(q)))
