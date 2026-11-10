"""Make the AI's own lines read like a person typing in Twitch chat, not an assistant.
Only used on AI-written replies - Maddi's real quotes are never touched."""
import re

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]+")
# assistant-y endings people don't really type
FILLER_END = re.compile(
    r"[\s,.!?-]*\b(what'?s up|wbu|how about you|what about you|how are you( doing)?|how'?s it going|"
    r"hbu|how can i help( you)?( today)?|anything else|what'?s new|what are you up to|(and|n|wbu) (you|u)\?)\s*[?!.]*\s*$", re.I)
OPENER = re.compile(r"^(hey there|hello there|hi there|hey friend|greetings)\b[\s,!.]*", re.I)


def shorten(t: str, max_words: int) -> str:
    """At most 2 sentences and max_words words - cut at a sentence end when we can."""
    sents = re.split(r"(?<=[.!?])\s+", t.strip())
    out = " ".join(sents[:2])
    words = out.split()
    if len(words) <= max_words:
        return out
    cut = " ".join(words[:max_words])
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[:end + 1] if end > len(cut) // 3 else cut


def drop_banned(t: str, never) -> str:
    """Remove any sentence that contains a 'never say' phrase."""
    if not never:
        return t
    sents = re.split(r"(?<=[.!?])\s+", t)
    keep = [x for x in sents if not any(n in x.lower() for n in never)]
    return " ".join(keep).strip(" ,")


def humanize(s: str, keep_emoji: bool = False, max_words: int = 0, never=()) -> str:
    if not s:
        return s
    s = drop_banned(s, never)
    if not s:
        return ""
    if max_words:
        s = shorten(s, max_words)
    t = s if keep_emoji else EMOJI.sub("", s)
    t = OPENER.sub("hey ", t)
    for _ in range(2):                       # "hey bro! what's up?" -> "hey bro"
        stripped = FILLER_END.sub("", t)
        if len(stripped.split()) >= 1:
            t = stripped
    t = re.sub(r"!+", "", t)                 # nobody chill uses "!" every line
    t = re.sub(r"\s+([,.?])", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[.]$", "", t)               # no period at the end of a chat line
    t = t.lower()
    t = re.sub(r"\bi\b", "i", t)
    return t.strip(" ,") or s.strip().lower()
