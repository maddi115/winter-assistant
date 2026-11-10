"""Openers and 'idk' lines, by verdict and tone. Rotated so replies don't repeat."""
import itertools

OPENERS = {
    ("YES", "casual"): ["For sure.", "Oh yeah.", "Yeah, 100%.", "Hell yeah."],
    ("YES", "neutral"): ["Yes.", "I do.", "Yeah, I do."],
    ("NO", "casual"): ["Nah.", "Not really, no.", "Nope."],
    ("NO", "neutral"): ["No.", "Not really.", "I don't, no."],
    ("UNCLEAR", "casual"): ["Hmm, not sure I'd say that.", "Kinda? Idk.", "Not sure honestly."],
    ("UNCLEAR", "neutral"): ["Not sure I'd say that exactly.", "Hard to say."],
    ("CHANGED", "casual"): ["I've gone back and forth on that.", "Changed my mind on that one."],
    ("CHANGED", "neutral"): ["I've changed my mind on that over time."],
    ("FOUND", "casual"): ["Okay so,", "Honestly,", "Lol okay,", "Ngl,", "For real,"],
    ("FOUND", "neutral"): ["Here's what I've said:", "So,", "Well,", "Honestly,"],
    ("IDK", "casual"): ["idk honestly, I've never really said.", "No clue tbh, never talked about that.",
                        "Hmm, I don't think I've ever said anything about that."],
    ("NOMORE", "casual"): ["That's all I've got on that lol.", "Nah that's all I've said about it."],
    ("NOMORE", "neutral"): ["That's all I've said about that."],
    ("PRIVATE", "casual"): ["nah that's private lol.", "I'd rather keep that one to myself tbh."],
    ("PRIVATE", "neutral"): ["That's private, sorry.", "I'd rather keep that to myself."],
    ("NOPE", "casual"): ["lol nah.", "nice try lol.", "nah I'm good 😂"],
    ("NOPE", "neutral"): ["I'm not going to do that.", "Nice try."],
    ("IDK", "neutral"): ["I don't think I've ever said anything about that.",
                         "I honestly don't know, I've never talked about it."],
}

_cycles = {}


def pick(kind: str, tone: str) -> str:
    key = (kind, tone) if (kind, tone) in OPENERS else (kind, "neutral")
    if key not in _cycles:
        _cycles[key] = itertools.cycle(OPENERS[key])
    return next(_cycles[key])
