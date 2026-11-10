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
    return re.findall(r"[a-z0-9]+", text.lower().replace("'", "").replace("’", ""))


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


# ---------- actions: "did you fall off your bike?" -> "I fell off my bike" = yes ----------
IRREGULAR = {
    "fall": ["fell", "fallen"], "give": ["gave", "given"], "eat": ["ate", "eaten"],
    "drink": ["drank", "drunk"], "go": ["went", "gone"], "get": ["got", "gotten"],
    "buy": ["bought"], "ride": ["rode", "ridden"], "see": ["saw", "seen"], "make": ["made"],
    "do": ["did", "done"], "run": ["ran"], "swim": ["swam"], "sing": ["sang"],
    "drive": ["drove", "driven"], "write": ["wrote"], "take": ["took"], "come": ["came"],
    "win": ["won"], "lose": ["lost"], "break": ["broke", "broken"], "think": ["thought"],
    "feel": ["felt"], "meet": ["met"], "leave": ["left"], "sell": ["sold"], "pay": ["paid"],
    "have": ["had", "has", "having", "got"], "smoke": ["smoked"], "cook": ["cooked"],
}
FEELING_VERBS = {"like", "love", "enjoy", "hate", "dislike", "adore", "prefer"}
HABIT_VERBS = {"drink", "eat", "play", "watch", "listen", "use", "wear", "ride", "smoke", "cook"}
MODALS = {"wanna", "want", "might", "should", "could", "would", "will", "gonna", "wish", "may",
          "if", "maybe", "hope", "tryna", "planning", "plan", "need", "gotta"}
SUBJECT = {"i", "we", "im", "ive", "id"}
OTHERS = {"he", "him", "she", "her", "they", "them", "you", "u", "ya", "someone", "somebody", "people",
          "hes", "shes", "theyre", "youre", "ur", "bro", "dude", "chat", "everyone"}


def verb_forms(v: str):
    forms = {v, v + "s", v + "ed", v + "d", v + "ing", v + "es"}
    if v.endswith("e"):
        forms.add(v[:-1] + "ing")
    if len(v) > 2 and v[-1] not in "aeiouwy" and v[-2] in "aeiou":
        forms |= {v + v[-1] + "ing", v + v[-1] + "ed"}       # run -> running, stop -> stopped
    return forms | set(IRREGULAR.get(v, []))


def action_polarity(text: str, verbs) -> int:
    """+1 'I fell / I give / I drink', -1 'I never / I dont give', 0 not stated or only wished."""
    toks = _tokens(text)
    forms = set()
    for v in verbs:
        forms |= verb_forms(v)
    for i, t in enumerate(toks):
        if t not in forms:
            continue
        window = toks[max(0, i - 4):i]
        people = [w for w in window if w in SUBJECT or w in OTHERS]
        if not people or people[-1] not in SUBJECT:   # "i saw HIM eat" -> he ate, not me
            continue
        if MODALS & set(window):              # "i wanna", "i might", "i wish": not done
            continue
        return -1 if NEGATORS & set(window) else 1
    return 0


def possesses(text: str, thing: str) -> bool:
    """'do you have a dog?' needs 'my dog' / 'i got a dog', not 'my dad left the dog'."""
    from retrieval.gradient import stem
    toks = _tokens(text)
    for i, t in enumerate(toks):
        if stem(t) == thing:
            window = toks[max(0, i - 4):i]
            if window[-3:] and "my" in window[-3:]:
                return True
            if {"having"} & set(window) or (SUBJECT & set(window) and
                                              {"have", "got", "had", "own", "ive", "getting"} & set(window)):
                return True
    return False


def mentions_object(text: str, objects) -> bool:
    """'did you fall off your bike?' -> the answer must say 'bike' too
    (so 'i fall in love' doesn't count)."""
    if not objects:
        return True
    from retrieval.gradient import stem
    toks = {stem(t) for t in _tokens(text)}
    return any(o in toks for o in objects)


def decide(vessels: List[Dict], flip: bool = False, verb: str = None,
           objects=None) -> Tuple[str, bool, List[Dict]]:
    """Returns (verdict, changed_mind, vessels ordered for display).
    verb = the question's verb ("fall" in "did you fall off your bike?"),
    objects = the question's other words ("bike")."""
    def score(v):
        if v.get("is_question"):              # "do you like X?" isn't a statement about me
            return 0
        if verb and verb not in FEELING_VERBS:
            # "did you fall off your bike?": only the action counts, and it must be about the bike
            # ("i like girls who... i fall in love" says nothing about bikes)
            if not mentions_object(v["text"], objects):
                return 0
            return action_polarity(v["text"], [verb]) or polarity(v["text"]) * 0
        p = polarity(v["text"])                # feelings: "i love it", "i hate it"
        if p == 0 and (not verb or verb in FEELING_VERBS):
            # "i drink that stuff in 1 day" -> yes; but "i dont eat X anymore" isn't "i hate X"
            p = max(0, action_polarity(v["text"], HABIT_VERBS))
        return p
    scored = [(v, score(v)) for v in vessels]
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
