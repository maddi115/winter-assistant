"""When should Winter talk? Like a person in chat: answer when spoken to,
otherwise only sometimes, and never take over the chat.

  direct        @winter, a reply to winter, !winter, saying my name          -> always
  meow          sometimes (40% home / 20% guest) and never twice within 45s / 3 min
  guest channel (not mine): no 1-on-1 rule, rarer joining in, "winter" alone isn't my name
  aimed at someone else  (@otherguy ..., replying to someone)               -> never
  just a reaction  ("ICANT", "KEKW", "omg", "😹")                            -> never (unless it's to me)
  chat flying (60+ msgs/min)                                                 -> only when talked to
  1-on-1        only one person chatting lately (home)                       -> usually (the AI may skip)
  everything else -> only at a real MOMENT, never at random:
     catch up           "what are they doing?" "what happened?"              -> maybe: fill them in from the stream
     question to chat   "anyone played this?" "who's winning?"               -> maybe (AI may skip)
     chat on one topic  3+ people on the same thing (checked on the chat)    -> maybe (AI may skip)
     chat mood          3+ people laughing / shocked / grossed out / hype     -> maybe ONE emote (own budget)
  ...and only within a budget: 2 per 15 min as a guest, 4 at home, plus a gap between them
Starting a conversation on my own (silence, welcome back) lives in twitch/self_talk.py.
"""
import random
import re

from core.reflexes import reflex
from twitch.emotes import is_reaction
from twitch.rules import Incoming, question_for_bot


ASKS_CHAT = re.compile(r"^(anyone|any1|anybody|does anyone|did anyone|has anyone|who|what|which|where|when|why|how|"
                       r"is it|is this|are we|should|would|can|do (you|u) guys|chat|y'?all|yall)\b", re.I)
WAVE_REPLY = {"laugh": ["😹", "LUL"], "sad": ["🥀"], "hype": ["W"]}


CATCH_UP = re.compile(
    r"\b(what (are|r|is|s) (they|he|she|u|you|y'?all|you guys|u guys|we|sam) (doing|up to|talking about)"
    r"|what'?s (going on|happening|the plan)|what is (going on|happening)|what happened"
    r"|where (are|r|is) (they|he|she|u|you guys|u guys|y'?all|we)( at| going)?"
    r"|what did (he|she|they|sam) (just )?say|why (are|is) (they|he|she) )", re.I)


def catch_up(text: str) -> bool:
    """Someone just got here / missed something: 'what are you guys doing now?' 'what happened?'
    A regular would fill them in from what's on stream."""
    return text.strip().endswith("?") and bool(CATCH_UP.search(text))


def asks_chat(text: str) -> bool:
    """A real question thrown at the whole chat (not 'huh?')."""
    t = text.strip()
    return t.endswith("?") and len(t.split()) >= 3 and bool(ASKS_CHAT.match(t))


def wave_reply(mood_, allowed):
    """One emoji/emote for the wave - only ones I actually use."""
    allowed = allowed or ["😹", "🥀", "W"]
    for opt in WAVE_REPLY.get(mood_, []):
        if opt in allowed or opt == "W":
            return opt
    return None


def _on_topic(knows, text, room):
    try:
        return knows(text, room)
    except TypeError:                       # simple knows(text) from tests / older callers
        return knows(text)


def meow_or_not(text, room, c, guest, rng):
    """Meow back sometimes, not every time - and never meow-spam."""
    gap = c.twitch_meow_gap if guest else c.twitch_meow_gap_home
    if room.clock() - room.last_meow < gap:
        return None, "meowed recently"
    if rng() >= (c.twitch_meow_chance_guest if guest else c.twitch_meow_chance_home):
        return None, "let the meow go"
    return text, "meow"


def decide(m: Incoming, bot: str, c, room, rng=random.random, knows=None, emojis=None):
    """-> (text to answer or None, reason).
    knows(text, room) -> True if chat is having one real conversation around this message
    (the Twitch chat itself - never my own data). Only asked when a moment is possible."""
    guest = getattr(room, "guest", False)
    direct = question_for_bot(m, bot, c.twitch_prefix, c.twitch_ignore_users)
    if direct is not None:
        if reflex(direct):                  # "@winterrs0 meow" - calm about it too
            return meow_or_not(direct, room, c, guest, rng)
        return direct, "direct"
    if m.user == bot.lower() or m.user in {u.lower() for u in c.twitch_ignore_users}:
        return None, "ignored"
    if not c.twitch_reply_all:
        return None, "not for me"
    text = m.text.strip()
    if m.reply_to_user or m.mentions or re.search(r"(^|\s)@\w", text):
        return None, "talking to someone else"
    now = room.clock()
    # in someone else's chat "winter" is just a word ("winter break") - only my real name counts
    names = {bot.lower(), c.agent_label.lower(), "agentwinter"} | (set() if guest else {"winter"})
    called = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b[,:]?", re.I)
    if called.search(text):
        # "agentwinter whats ur name" -> "whats ur name" (so the question matches normally)
        return re.sub(r"\s+", " ", called.sub(" ", text)).strip(" ,:") or "hey", "said my name"
    if reflex(text):
        return meow_or_not(text, room, c, guest, rng)

    speed = room.mpm() if hasattr(room, "mpm") else 0.0
    budget = c.twitch_budget_15min_guest if guest else c.twitch_budget_15min_home
    gap = c.twitch_guest_chime_gap if guest else c.twitch_chime_gap
    room_ok = room.uninvited_since(900) < budget

    # chat mood: 3+ people laughing / shocked / grossed out... -> maybe ONE emote (own budget)
    from twitch import mood as MD
    if MD.mood_of(text) and MD.budget_ok(room, c, guest):
        mood_, lines_ = MD.room_mood(room, c.twitch_mood_seconds, c.twitch_mood_people)
        if mood_ and rng() < c.twitch_moment_mood:
            emote = MD.pick_emote(mood_, room, emojis or (), lines_)
            if emote:
                # claim the budget NOW: two laughs a second apart must not both send an emote
                # (that sent WutFace twice and Twitch blocked the 2nd as a duplicate)
                room.emote_times = list(getattr(room, "emote_times", [])) + [room.clock()]
                room.last_emote = emote
                return emote, "chat mood"
    # Twitch marks emotes (even the streamer's sub emotes) - a message that's only emotes is a reaction
    only_emotes = bool(getattr(m, "emotes", None)) and is_reaction(m.plain or "")
    if only_emotes or is_reaction(text):
        return None, "just a reaction"      # "ICANT", "KEKW", "omg", "😹" - nothing to answer
    if speed >= c.twitch_flying_mpm:
        return None, "chat is flying"       # only answer when someone talks to me
    if not guest:
        others = room.humans_since(c.twitch_one_on_one_sec) - {m.user}
        if not others:
            # 1-on-1 is a conversation, but not every line needs an answer
            if now - room.last_bot < c.twitch_home_reply_gap:
                return None, "just replied"
            if len(text.split()) == 1 and len(text) < 6 and not text.endswith("?") and rng() < c.twitch_noise_skip:
                return None, "tiny message"
            return text, "1-on-1"           # the AI may still skip it
    if now - room.last_chime < gap:
        return None, "spoke up recently"          # only counts when I actually SENT something
    if not room_ok:
        return None, "said enough lately"
    if now - getattr(room, "last_considered", -1e9) < c.twitch_consider_gap:
        return None, "thought about it recently"   # stayed quiet on a moment a minute ago

    # only a real moment can make me speak up - never a dice roll on random chat
    if catch_up(text) and (getattr(room, "heard", None) is not None or getattr(room, "stream", "")):
        moment, chance = "catch up", c.twitch_moment_catchup
    elif asks_chat(text):
        moment, chance = "question to chat", c.twitch_moment_question
    elif knows is not None and len(text.split()) >= 3 and _on_topic(knows, text, room):
        moment, chance = "chat on one topic", c.twitch_moment_topic
    else:
        return None, "no reason to jump in"
    if speed >= c.twitch_busy_mpm:
        chance /= 1 + speed / c.twitch_busy_mpm   # faster chat -> I speak up less
    if rng() < chance:
        return text, moment                  # the AI may still decide it has nothing good to add
    return None, f"{moment}, but let it go"
