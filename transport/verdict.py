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
NEG_PHRASES = [r"\bgross\b", r"\bnasty\b", r"\bdisgusting\b", r"\bnot a fan\b", r"\bcant stand\b",
               r"\be+w+\b", r"\byuck\b", r"\byucky\b"]
NEGATORS = {"not", "dont", "never", "no", "aint", "isnt", "doesnt", "didnt", "hardly", "barely",
            "wouldnt", "cant", "nah", "nope", "havent", "hasnt", "wont", "wasnt", "werent", "stopped", "quit"}
ADVERBS = {"really", "rly", "kinda", "lowkey", "highkey", "honestly", "actually", "even", "still", "do", "just",
           "fucking", "fuckin", "freaking", "fkn", "so", "totally", "literally", "genuinely", "def",
           "definitely", "absolutely", "truly", "also", "always", "usually", "sometimes", "now", "lowk"}


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


REVERSE_IRREGULAR = {past: base for base, pasts in IRREGULAR.items() for past in pasts}


def base_forms(v: str):
    """'hiked' -> {'hike', 'hik'}, 'used' -> {'use', 'us'}, 'went' -> {'go'}, 'tried' -> {'try'}."""
    out = {v}
    if v in REVERSE_IRREGULAR:
        out.add(REVERSE_IRREGULAR[v])
    if v.endswith("ied") and len(v) > 4:
        out.add(v[:-3] + "y")
    if v.endswith("ed") and len(v) > 3:
        out |= {v[:-2], v[:-1]}
        if v[-3] == v[-4]:
            out.add(v[:-3])                                  # stopped -> stop
    if v.endswith("ing") and len(v) > 5:
        out |= {v[:-3], v[:-3] + "e"}
    return out


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
        for b in base_forms(v):
            forms |= verb_forms(b)
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
            if "if" in toks[max(0, i - 6):i]:                  # "if u were my girlfriend" = hypothetical
                continue
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


def polarity_about(text: str, terms) -> int:
    """Like polarity(), but a feeling only counts if it points AT the thing:
    'i love hiking' -> +1 for hiking; 'i like ur ex... she posted on tea app' -> 0 for tea."""
    from retrieval.gradient import stem
    terms = set(terms or [])
    if not terms:
        return polarity(text)
    toks = _tokens(text)
    st = [stem(t) for t in toks]
    def near(i, after=8, before=4):
        return any(s in terms for s in st[i + 1:i + 1 + after]) or any(s in terms for s in st[max(0, i - before):i])
    score = 0
    for i, t in enumerate(toks):
        if t in POS_VERBS or t in NEG_VERBS:
            j = i - 1
            while j >= 0 and (toks[j] in ADVERBS or toks[j] in NEGATORS):
                j -= 1
            if j < 0 or toks[j] not in ("i", "we", "im"):
                continue
            # the thing must come right after the feeling, before another "i ..." starts
            k = i + 1
            while k < len(toks) and k <= i + 8 and toks[k] != "i":
                if st[k] in terms:
                    break
                k += 1
            pointed = not (k >= len(toks) or k > i + 8 or toks[k] == "i")
            # "i tried sushi again and i love IT now": it/that/them points back
            if not pointed and i + 1 < len(toks) and toks[i + 1] in ("it", "that", "them", "this", "those", "em", "these"):
                pointed = any(x in terms for x in st[max(0, i - 12):i])
            if not pointed:
                continue
            neg = _negated(toks, i)
            if t in POS_VERBS:
                score += -1 if neg else 1
            elif not neg:
                score -= 1
    clean = " ".join(toks)
    for pats, sign in ((POS_PHRASES, 1), (NEG_PHRASES, -1)):
        for p in pats:
            for m in re.finditer(p, clean):
                i = len(clean[:m.start()].split())
                before = clean[:m.start()].split()
                if not any(w in NEGATORS for w in before[-2:]) and near(i, after=4, before=8):
                    score += sign
    return (score > 0) - (score < 0)


def decide(vessels: List[Dict], flip: bool = False, verb=None,
           objects=None, subject=None) -> Tuple[str, bool, List[Dict]]:
    """Returns (verdict, changed_mind, vessels ordered for display).
    verb = the question's verb ("fall" in "did you fall off your bike?"),
    objects = the question's other words ("bike")."""
    verbs = verb if isinstance(verb, (list, set, tuple)) else ([verb] if verb else [])
    feeling_q = not verbs or any(v in FEELING_VERBS for v in verbs)

    def score(v):
        if v.get("is_question"):              # "do you like X?" isn't a statement about me
            return 0
        if subject and not mentions_object(v["text"], subject):
            return 0                          # "i hate sweet stuff" says nothing about coffee
        if not feeling_q:
            # "did you fall off your bike?": only the action counts, and it must be about the bike
            # ("i like girls who... i fall in love" says nothing about bikes)
            if not mentions_object(v["text"], objects):
                return 0
            return action_polarity(v["text"], verbs)
        p = polarity_about(v["text"], subject) if subject else polarity(v["text"])   # feelings about IT
        if p == 0:
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
