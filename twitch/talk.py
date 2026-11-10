"""When should Winter talk? Like a person in chat: answer when spoken to,
otherwise only sometimes, and never take over the chat.

  direct        @winter, a reply to winter, !winter, saying my name, meow    -> always
  guest channel (not mine): no 1-on-1 rule, rarer joining in, "winter" alone isn't my name
  aimed at someone else  (@otherguy ..., replying to someone)               -> never
  just a reaction  ("ICANT", "KEKW", "omg", "😹")                            -> never (unless it's to me)
  chat flying (60+ msgs/min)                                                 -> only when talked to
  1-on-1        only one person chatting lately (home)                       -> usually (the AI may skip)
  busy chat     several people talking                                       -> sometimes (chance + gap)
Starting a conversation on my own (silence, welcome back) lives in twitch/self_talk.py.
"""
import random
import re

from core.reflexes import reflex
from twitch.emotes import is_reaction
from twitch.rules import Incoming, question_for_bot


def decide(m: Incoming, bot: str, c, room, rng=random.random):
    """-> (text to answer or None, reason)"""
    direct = question_for_bot(m, bot, c.twitch_prefix, c.twitch_ignore_users)
    if direct is not None:
        return direct, "direct"
    if m.user == bot.lower() or m.user in {u.lower() for u in c.twitch_ignore_users}:
        return None, "ignored"
    if not c.twitch_reply_all:
        return None, "not for me"
    text = m.text.strip()
    if m.reply_to_user or m.mentions or re.search(r"(^|\s)@\w", text):
        return None, "talking to someone else"
    guest = getattr(room, "guest", False)
    gap = c.twitch_guest_chime_gap if guest else c.twitch_chime_gap
    # in someone else's chat "winter" is just a word ("winter break") - only my real name counts
    names = {bot.lower(), c.agent_label.lower(), "agentwinter"} | (set() if guest else {"winter"})
    called = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b[,:]?", re.I)
    if called.search(text):
        # "agentwinter whats ur name" -> "whats ur name" (so the question matches normally)
        return re.sub(r"\s+", " ", called.sub(" ", text)).strip(" ,:") or "hey", "said my name"
    if reflex(text):
        if guest and room.clock() - room.last_chime < gap:
            return None, "meowed recently"
        return text, "meow"
    if is_reaction(text):
        return None, "just a reaction"      # "ICANT", "KEKW", "omg", "😹" - nothing to answer
    speed = room.mpm() if hasattr(room, "mpm") else 0.0
    if speed >= c.twitch_flying_mpm:
        return None, "chat is flying"       # only answer when someone talks to me
    if not guest:
        others = room.humans_since(c.twitch_one_on_one_sec) - {m.user}
        if not others:
            # 1-on-1 is a conversation, but not every line needs an answer
            if room.clock() - room.last_bot < c.twitch_home_reply_gap:
                return None, "just replied"
            if len(text.split()) == 1 and len(text) < 6 and not text.endswith("?") and rng() < c.twitch_noise_skip:
                return None, "tiny message"
            return text, "1-on-1"           # the AI may still skip it
    if room.clock() - room.last_chime < gap:
        return None, "chimed in recently"
    chance = (c.twitch_guest_chime_chance if guest else c.twitch_chime_chance) * (2 if text.endswith("?") else 1)
    if speed >= c.twitch_busy_mpm:
        chance /= 1 + speed / c.twitch_busy_mpm   # faster chat -> I join in less
    if rng() < chance:
        return text, "chimed in"        # the AI may still decide it has nothing good to add
    return None, "letting them talk"
