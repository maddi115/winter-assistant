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
    """Is the visitor asking about the owner? ('do you...', 'your...', by name,
    a bare 'coffee or soda?', or 'fav food??')"""
    t = norm(q)
    if re.search(r"\b(you|your|yours|yourself|u|ur|ya)\b", t):
        return True
    if not re.search(r"\b(i|me|my|mine)\b", t):          # not the visitor talking about themselves
        if re.search(r"\b(fav|fave|favorite|favourite)\b", t) or compare_options(q):
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


QVERB = re.compile(r"^(?:do|does|did|would|will|can|could|have|has)\s+(?:you|u|ya)\s+"
                   r"(?:ever\s+|still\s+|really\s+|even\s+|usually\s+|actually\s+)*([a-z]+)")


def question_verb(q: str):
    """'did you ever fall off your bike' -> 'fall'; 'have you been to paris' -> None."""
    m = QVERB.match(norm(q).rstrip("?").strip())
    if not m:
        return None
    v = m.group(1)
    return None if v in ("been", "be", "a", "an", "the", "any") else v


def asks_possession(q: str) -> bool:
    """'do you have a dog?' / 'do you own a car?' / 'you got a gf?'"""
    t = norm(q)
    return bool(re.match(r"^(do|did)\s+(you|u)\s+(have|own|got)\b|^(you|u)\s+(have|got|own)\b|"
                         r"^have\s+(you|u)\s+got\b", t))


def compare_options(q: str):
    """'do you like cheetos or burritos more?' -> ('cheetos', 'burritos'), else None."""
    from retrieval.gradient import content_terms, tokenize
    t = norm(q).rstrip("?").strip()
    if " or " not in t:
        return None
    left, right = t.split(" or ", 1)
    right = re.sub(r"\b(more|better|most|best|rn|tho|though|lol)\b", " ", right)
    lt, rt = content_terms(left), content_terms(right)
    if not lt or not rt:
        return None
    lw = [w for w in tokenize(left) if content_terms(w) == [lt[-1]]]
    rw = [w for w in tokenize(right) if content_terms(w) == [rt[0]]]
    return (lt[-1], lw[-1] if lw else lt[-1]), (rt[0], rw[0] if rw else rt[0])


def private_pattern(topics):
    words = [re.escape(t.lower()) for t in topics if t.strip()]
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I) if words else None


def is_private(text: str, topics) -> bool:
    pat = private_pattern(topics)
    return bool(pat and pat.search(text.lower().replace("’", "'")))


SLANG_VERBS = [(r"\b(fw|fwm|fuck with|fucks with|fuckin with|fucking with|rock with|vibe with|mess with)\b", "like"),
         (r"\bfav\b", "favorite"), (r"\bfave\b", "favorite")]


def unslang(q: str) -> str:
    """'do u fw kombucha' -> 'do u like kombucha'."""
    t = q
    for pat, rep in SLANG_VERBS:
        t = re.sub(pat, rep, t, flags=re.I)
    return t


def question_verbs(q: str):
    """All base forms of the question's verb: 'have you hiked' -> ['hiked', 'hike', 'hik']."""
    from transport.verdict import base_forms
    v = question_verb(q)
    return sorted(base_forms(v)) if v else []
