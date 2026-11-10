"""When should Winter talk? Like a person in chat: answer when spoken to,
otherwise only sometimes, and never take over the chat.

  direct        @winter, a reply to winter, !winter, saying "winter", meow  -> always
  aimed at someone else  (@otherguy ..., replying to someone)               -> never
  1-on-1        only one person chatting lately                              -> always
  busy chat     several people talking                                       -> sometimes (chance + gap)
Starting a conversation on my own (silence, welcome back) lives in twitch/self_talk.py.
"""
import random
import re

from core.reflexes import reflex
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
    names = {bot.lower(), c.agent_label.lower(), "winter"}
    if any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in names) or reflex(text):
        return text, "said my name"
    others = room.humans_since(c.twitch_one_on_one_sec) - {m.user}
    if not others:
        return text, "1-on-1"
    if room.clock() - room.last_chime < c.twitch_chime_gap:
        return None, "chimed in recently"
    chance = c.twitch_chime_chance * (2 if text.endswith("?") else 1)
    if rng() < chance:
        return text, "chimed in"
    return None, "letting them talk"
