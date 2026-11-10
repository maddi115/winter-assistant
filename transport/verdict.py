"""Coarse level: YES / NO / UNCLEAR from what you actually said. Pure rules.

Fixes vs maddis-rag:
  - whole-word matching ("no" no longer matches inside "know" / "not")
  - negation check: "i dont like", "not really a fan", "i dont hate it"
  - nothing clear -> UNCLEAR (never a default YES)
  - when quotes disagree, the NEWEST one wins (people change their minds)
"""
import re
from typing import List, Dict, Tuple

POS_VERBS = {"like", "love", "enjoy", "adore", "luv", "liked", "loved", "enjoyed"}
NEG_VERBS = {"hate", "dislike", "despise", "hated", "disliked"}
POS_PHRASES = [r"\bawesome\b", r"\bamazing\b", r"\bdelicious\b", r"\bso good\b", r"\bthe best\b",
               r"\bmy fav(orite|ourite|e)?\b", r"\bguilty pleasure\b", r"\bobsessed\b"]
NEG_PHRASES = [r"\bgross\b", r"\bnasty\b", r"\bdisgusting\b", r"\bnot a fan\b", r"\bcant stand\b"]
NEGATORS = {"not", "dont", "never", "no", "aint", "isnt", "doesnt", "didnt", "hardly", "barely",
            "wouldnt", "cant", "nah", "nope"}
ADVERBS = {"really", "rly", "kinda", "lowkey", "honestly", "actually", "even", "still", "do", "just"}


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z]+", text.lower().replace("'", "").replace("’", ""))


def _negated(toks: List[str], i: int, lookback: int = 3) -> bool:
    return any(t in NEGATORS for t in toks[max(0, i - lookback):i])


def polarity(text: str) -> int:
    """+1 likes it, -1 doesn't, 0 unclear."""
    toks = _tokens(text)
    score = 0
    for i, t in enumerate(toks):
        if t in POS_VERBS or t in NEG_VERBS:
            # must be the speaker's own feeling: "i (really) like", not "its like"
            j = i - 1
            while j >= 0 and (toks[j] in ADVERBS or toks[j] in NEGATORS):
                j -= 1
            if j < 0 or toks[j] not in ("i", "we", "im"):
                continue
            neg = _negated(toks, i)
            if t in POS_VERBS:
                score += -1 if neg else 1
            elif not neg:                 # "i dont hate it" -> unclear, not a like
                score -= 1
    clean = " ".join(toks)
    for p in POS_PHRASES:
        for m in re.finditer(p, clean):
            before = clean[:m.start()].split()
            if not any(w in NEGATORS for w in before[-2:]):
                score += 1
    for p in NEG_PHRASES:
        for m in re.finditer(p, clean):
            before = clean[:m.start()].split()
            if not any(w in NEGATORS for w in before[-2:]):
                score -= 1
    return (score > 0) - (score < 0)


def decide(vessels: List[Dict], flip: bool = False) -> Tuple[str, bool, List[Dict]]:
    """Returns (verdict, changed_mind, vessels ordered for display)."""
    # questions ("do you like X?") aren't statements about me
    scored = [(v, 0 if v.get("is_question") else polarity(v["text"])) for v in vessels]
    pos = [v for v, p in scored if p > 0]
    neg = [v for v, p in scored if p < 0]
    changed = bool(pos and neg)
    if changed:
        newest = max(pos + neg, key=lambda v: v.get("date") or "")
        verdict = "YES" if newest in pos else "NO"
        ordered = sorted(pos + neg, key=lambda v: v.get("date") or "", reverse=True)
    elif pos:
        verdict, ordered = "YES", pos      # only quotes that back the verdict
    elif neg:
        verdict, ordered = "NO", neg
    else:
        verdict, ordered = "UNCLEAR", vessels
    if flip and verdict in ("YES", "NO"):
        verdict = "NO" if verdict == "YES" else "YES"
    return verdict, changed, ordered
