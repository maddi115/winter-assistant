"""Checker: the AI's few words must not add facts. Bad output -> template fallback."""
import json
import re
from typing import List, Optional, Set

BANNED = [r"\byou said\b", r"\bas an ai\b", r"\baccording to\b", r"\bthe (quote|evidence|source)s?\b",
          r"\bnumber \d\b", r"\[\d", r"\bhe said\b", r"\bshe said\b", r"\bthey said\b"]


def parse_reply(raw: str):
    """Forgiving parser: works even if a tiny model returns messy text."""
    picks, opener = [], ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            p = data.get("pick", data.get("picks", []))
            if isinstance(p, (int, str)):
                p = [p]
            for x in p or []:
                for n in re.findall(r"\d+", str(x)):
                    picks.append(int(n))
            opener = str(data.get("opener", "") or "")
            return picks, opener
    except Exception:
        pass
    if re.search(r"\bnone\b", raw.lower()):
        return [], ""
    return [int(n) for n in re.findall(r"\b\d{1,2}\b", raw)], ""


def clean_picks(picks: List[int], n: int) -> List[int]:
    out = []
    for p in picks:
        if 1 <= p <= n and p not in out:
            out.append(p)
    return out


def _words(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower().replace("'", "")))


def check_opener(opener: str, evidence: List[str], question: str, persona: str,
                 max_words: int) -> Optional[str]:
    """Return a safe opener, or None if it must be replaced by a template."""
    t = re.sub(r"\s+", " ", (opener or "").strip().strip('"“”')).strip()
    if not t:
        return None
    if len(t.split()) > max_words:
        return None
    low = t.lower()
    if any(re.search(p, low) for p in BANNED):
        return None
    allowed = _words(" ".join(evidence) + " " + question + " " + persona)
    # no numbers that aren't in the evidence or question
    for num in re.findall(r"\d+", t):
        if num not in allowed:
            return None
    # no names / proper nouns that aren't in the evidence or question
    tokens = t.split()
    for i, w in enumerate(tokens):
        bare = re.sub(r"[^\w']", "", w)
        if not bare or bare in ("I", "I'm", "I've", "I'll", "I'd", "Idk", "OK", "Ok", "Lol", "LOL"):
            continue
        sentence_start = i == 0 or tokens[i - 1][-1:] in ".!?"
        if bare[0].isupper() and not sentence_start and bare.lower().replace("'", "") not in allowed:
            return None
    if t[-1].isalnum():
        t += "."
    return t
