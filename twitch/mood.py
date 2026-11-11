"""Chat mood -> one emote, no words. The safest way to join in: one emote can't be incoherent.

  3+ people share a mood within ~20s  ->  maybe react with ONE emote
  moods: laugh 😹/ICANT/KEKW · shock HUH · cringe 😭 · sad 🥀 · hype W/Pog · food Kreygasm · awkward 💀
  uses the emotes THIS chat uses (never sub emotes), my 🙏 😹 🥀 as backup
  own budget (separate from words), never the same emote twice in a row, never on hateful bait
"""
import re

from twitch.emotes import TOKEN, LAUGH, _CANON

LEX = {
    "laugh": {"icant", "kekw", "lul", "lulw", "omegalul", "kek", "kekl", "lmao", "lmfao", "lol", "xdd", "xd",
              "haha", "hahaha", "dead", "crying", "pepelaugh", "4head"},
    "shock": {"huh", "what", "wtf", "ayo", "ayoo", "ayooo", "wait", "nah", "bro", "noway", "wild", "omg", "monkaw",
              "wutface", "aware", "stare"},
    "cringe": {"ew", "eww", "ewww", "ewwww", "yuck", "nasty", "gross", "cringe", "disgusting", "ick", "yikes"},
    "sad": {"sadge", "pepehands", "biblethump", "feelsbadman", "notlikethis", "f", "rip", "o7", "deadge", "noo",
            "nooo", "noooo", "sad"},
    "hype": {"w", "pog", "pogchamp", "poggers", "pogu", "letsgo", "lets", "go", "gg", "ez", "gigachad", "clip",
             "goated", "insane", "batchest"},
    "food": {"yum", "yumm", "yummy", "kreygasm", "delicious", "tasty", "drooling", "hungry", "mmm", "mmmm"},
    "awkward": {"bruh", "awkward", "uhh", "uhhh", "um", "hmm", "clueless", "monkas"},
}
EMOJI_MOOD = {"😹": "laugh", "😂": "laugh", "🤣": "laugh", "💀": "awkward", "😳": "shock", "😱": "shock",
              "🤢": "cringe", "🤮": "cringe", "😭": "cringe", "🥀": "sad", "😢": "sad", "💔": "sad",
              "🔥": "hype", "🤤": "food", "😋": "food"}
# emotes that carry a mood even at the end of a longer line
ENDERS = {"kekw": "laugh", "icant": "laugh", "lul": "laugh", "lulw": "laugh", "omegalul": "laugh", "kek": "laugh",
          "lmao": "laugh", "lmfao": "laugh", "lol": "laugh", "huh": "shock", "wtf": "shock", "wow": "shock",
          "kreygasm": "food", "sadge": "sad", "wutface": "cringe"}
# what I'd post for each mood if the chat isn't using a fitting emote
DEFAULT = {"laugh": ["ICANT", "KEKW", "LUL", "😹"], "shock": ["HUH", "WutFace", "😳"], "cringe": ["😭"],
           "sad": ["🥀", "BibleThump"], "hype": ["W", "Pog", "🔥"], "food": ["Kreygasm"], "awkward": ["💀"]}
# (BTTV/7TV ones like ICANT / HUH / Pog are only used when twitch_third_party_emotes is on)
HATE = {"black", "white", "asian", "mexican", "indian", "arab", "arabian", "saudi", "jew", "jewish", "muslim",
        "immigrant", "illegal", "retard", "middle-eastern", "race", "racist", "culture"}


def mood_of(text: str):
    """The mood of a SHORT chat line (or None). 'ICANT', 'EWWW', 'AYOOOO', 'oh yum', 'W' ..."""
    t = (text or "").strip()
    if not t:
        return None
    for ch, m in EMOJI_MOOD.items():
        if ch in t:
            return m
    words = [w.lower() for w in TOKEN.findall(t)]
    if not words:
        return None
    if len(words) > 5:
        # "sam you look handsome until you open your mouth KEKW" - the emote at the end is the mood
        last = words[-1]
        if last in ENDERS and len(words) <= 20:
            return ENDERS[last]
        return None                         # long lines are talk, not a mood
    if len(words) > 1:
        # 2-5 words: the mood word has to lead or end the line, or be half of it
        # ("ICANT this guy", "the ultimatum lol", "oh yum") - not "what is this food called"
        edge = {words[0], words[-1]}
        hits = [w for w in words if any(w in lex for lex in LEX.values()) or LAUGH.match(w)]
        if not (edge & set(ENDERS) or edge & LEX["food"] or len(hits) * 2 >= len(words)):
            return None
    votes = {}
    for w in words:
        w2 = re.sub(r"(.)\1{2,}", r"\1\1", w)           # "ewwwww" -> "eww", "ayoooo" -> "ayoo"
        for m, lex in LEX.items():
            if w in lex or w2 in lex or (m == "laugh" and LAUGH.match(w)) or (m == "cringe" and re.match(r"^e+w+$", w)) \
                    or (m == "shock" and re.match(r"^ay+o+$", w)) or (m == "sad" and re.match(r"^no{3,}$", w)):
                votes[m] = votes.get(m, 0) + 1
    if not votes:
        return None
    return max(votes, key=votes.get)


def room_mood(room, seconds=20, people=3):
    """-> (mood, lines) if 3+ different people share one mood right now, else (None, [])."""
    cut = room.clock() - seconds
    by = {}
    for l in room.lines:
        if l.is_bot or l.ts < cut:
            continue
        m = mood_of(l.text)
        if m:
            by.setdefault(m, []).append(l)
    best, lines = None, []
    for m, ls in by.items():
        if len({l.user for l in ls}) >= people and len(ls) > len(lines):
            best, lines = m, ls
    if best is None:
        return None, []
    # never pile onto bait about race / where people are from
    recent = [l for l in room.lines if not l.is_bot and l.ts >= cut - 30]
    if any(set(w.lower() for w in TOKEN.findall(l.text)) & HATE for l in recent):
        return None, []
    return best, lines


def pick_emote(mood, room, mine=(), lines=()):
    """The room's own emote for this mood (what people are actually spamming), else my default.
    Never a sub emote, never the same one I just used."""
    usable = set(room.usable_emotes(window=300, people=2)) if hasattr(room, "usable_emotes") else set()
    last = getattr(room, "last_emote", None)
    counts = {}
    for l in lines:
        for w in set(TOKEN.findall(l.text)):
            if w in usable and mood_of(w) == mood:
                counts[w] = counts.get(w, 0) + 1
        for ch in EMOJI_MOOD:
            if ch in l.text and EMOJI_MOOD[ch] == mood and ch in (mine or ()):
                counts[ch] = counts.get(ch, 0) + 1
    ranked = sorted(counts, key=counts.get, reverse=True)
    native_only = getattr(room, "native_only", False)
    renders = getattr(room, "renders", lambda e: True)

    def ok_default(e):
        if not any(ch.isalnum() for ch in e) or e == "W":
            return True                                  # emoji / plain "W" always show fine
        if native_only:
            return renders(e)                            # Twitch global only (LUL, WutFace, Kreygasm...)
        return e in usable or e in ("HUH",) or e.lower() in _CANON

    options = ranked + [e for e in DEFAULT.get(mood, []) if ok_default(e)]
    for e in options:
        if e != last and e not in getattr(room, "sub_emotes", set()):
            return e
    return None


def budget_ok(room, c, guest):
    """Emotes have their own budget - separate from words."""
    now = room.clock()
    times = [t for t in getattr(room, "emote_times", []) if now - t < 900]
    room.emote_times = times
    cap = c.twitch_emote_per_15min_guest if guest else c.twitch_emote_per_15min_home
    if len(times) >= cap:
        return False
    return not times or now - times[-1] >= c.twitch_emote_gap
