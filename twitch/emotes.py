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


def is_reaction(text: str) -> bool:
    """Only emotes / emojis / 'lol'-type reactions - nothing to answer."""
    t = (text or "").strip()
    if not t:
        return True
    if EMOJI_ONLY.match(t):            # just emojis or punctuation
        return True
    words = TOKEN.findall(t)
    return 0 < len(words) <= 4 and all(w.lower() in NOISE for w in words)


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
