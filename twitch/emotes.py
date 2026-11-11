"""Twitch emotes: what they mean, so the AI doesn't read "ICANT" as the words "I can't".

  * emote-only messages ("ICANT", "KEKW KEKW", "omg") are reactions, not things to answer
  * the AI gets a short cheat sheet for emotes it sees in chat
  * emote names keep their exact capitals when the bot uses one (KEKW, not kekw - lowercase doesn't render)
Note: LUL, Kappa, BibleThump... are Twitch's own and show for everyone.
      KEKW, ICANT, OMEGALUL... are BTTV/FFZ/7TV and only show as pictures for viewers with those extensions.
"""
import re

MEANING = {
    "ICANT": "dying laughing", "KEKW": "laughing hard", "LUL": "laughing", "LULW": "laughing",
    "OMEGALUL": "laughing really hard", "KEKL": "laughing", "xdd": "laughing",
    "Pog": "hype / amazed", "PogChamp": "hype / amazed", "POGGERS": "hype", "PogU": "hype",
    "monkaS": "nervous", "monkaW": "scared", "Sadge": "sad", "PepeHands": "sad", "BibleThump": "sad / crying",
    "Kappa": "sarcasm / joking", "Clueless": "acting clueless (ironic)", "Aware": "uh-oh realization",
    "Copium": "coping", "Susge": "suspicious", "5Head": "big brain", "4Head": "laughing at a bad joke",
    "WutFace": "disgusted / wtf", "ResidentSleeper": "boring", "catJAM": "vibing to music",
    "catDance": "vibing", "EZ": "that was easy", "GIGACHAD": "based / confident", "Kreygasm": "pleasure / so good",
    "HUH": "confused", "o7": "salute / respect", "Stare": "staring", "peepoHappy": "happy",
    "YEP": "yep / agreeing", "NOPERS": "nope", "COPIUM": "coping", "Kek": "laughing", "KEK": "laughing",
    "FeelsBadMan": "sad", "FeelsGoodMan": "happy", "NotLikeThis": "disappointed", "TriHard": "excited",
    "BatChest": "hype (cringe on purpose)", "Deadge": "dead / so over",
    "Bedge": "going to sleep", "Okayge": "it's okay", "Madge": "mad", "pepeLaugh": "laughing knowingly",
}
_CANON = {k.lower(): k for k in MEANING}
# short reactions that aren't worth an answer on their own
NOISE = set(_CANON) | {"lol", "lmao", "lmfao", "omg", "xd", "haha", "hahaha", "hah", "lul", "w", "l", "gg",
                       "ggs", "f", "rip", "wow", "ok", "k", "kk", "bruh", "damn", "ayo", "yoo", "nah",
                       "true", "real", "fr", "same", "?", "??", "???", "!", "o7", "uhh", "hmm", "huh"}
TOKEN = re.compile(r"[A-Za-z0-9?!]+")
EMOJI_ONLY = re.compile(r"^[\W_]+$")


CAMEL = re.compile(r"^[a-z]*[A-Z][a-z]+[A-Z][A-Za-z0-9]*$|^[A-Z]{3,}[a-z]*$|^[a-z]+[A-Z]{2,}[a-z]*$"
                   r"|^[a-z][a-z0-9]{2,9}[A-Z][A-Za-z0-9]{1,20}$")   # sub emotes: scentlHere4U, mvngoDizzy, jenn1eDaisyGG
LAUGH = re.compile(r"^(a?h+a+h+[ah]*|a?ha(ha)+h?|l+o+l+[ol]*|lmf?a+o+|xd+|ja(ja)+|kek+|rofl)$", re.I)


def looks_like_emote(w: str) -> bool:
    """RaccAttack, catJAM, Kreygasm... - emotes we don't have on the list."""
    return bool(CAMEL.match(w)) and len(w) <= 20


def is_reaction(text: str) -> bool:
    """Only emotes / emojis / 'lol'-type reactions - nothing to answer."""
    t = (text or "").strip()
    if not t:
        return True
    if EMOJI_ONLY.match(t):            # just emojis or punctuation
        return True
    words = TOKEN.findall(t)
    return 0 < len(words) <= 4 and all(w.lower() in NOISE or LAUGH.match(w) or looks_like_emote(w) for w in words)


SAD = {"sadge", "pepehands", "biblethump", "feelsbadman", "notlikethis", "f", "rip", "o7", "deadge"}
HYPE = {"pog", "pogchamp", "poggers", "pogu", "w", "ez", "gigachad", "lets", "go", "letsgo", "batchest"}
SAD_EMOJI = "🥀😢😭💔🕊"


def mood(text: str) -> str:
    """laugh / sad / hype / other - for joining a chat wave."""
    t = (text or "")
    if any(ch in t for ch in SAD_EMOJI):
        return "sad"
    if any(ch in t for ch in "😹😂🤣💀"):
        return "laugh"
    words = [w.lower() for w in TOKEN.findall(t)]
    if words and all(w in SAD for w in words):
        return "sad"
    if words and all(w in HYPE for w in words):
        return "hype"
    if words and any(LAUGH.match(w) or MEANING.get(_CANON.get(w, ""), "").startswith("laugh")
                     or MEANING.get(_CANON.get(w, ""), "") == "dying laughing" for w in words):
        return "laugh"
    return "other"


def found(text: str):
    return [_CANON[w.lower()] for w in TOKEN.findall(text or "") if w.lower() in _CANON]


def cheat_sheet(lines) -> str:
    """'ICANT = dying laughing; KEKW = laughing hard' for emotes seen in these chat lines."""
    seen = []
    for l in lines:
        for e in found(l):
            if e not in seen:
                seen.append(e)
    return "; ".join(f"{e} = {MEANING[e]}" for e in seen[:8])


def fix_case(text: str) -> str:
    """kekw -> KEKW (emote names are case-sensitive)."""
    return re.sub(r"[A-Za-z0-9]+", lambda m: _CANON.get(m.group(0).lower(), m.group(0)), text)
