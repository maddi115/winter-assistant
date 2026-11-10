"""Winter speaking up on her own - rarely, like a chill regular, never a hype bot.

Two reasons to start talking:
  silence   chat had a real convo, then went quiet  -> one line about what people said
  welcome   a regular comes back after a while, and chat is busy so I wasn't going to
            answer them anyway                      -> a quick "yo welcome back" (sometimes)

Hard limits so it never gets chatty:
  * at most twitch_self_max_per_hour self-started messages per hour, per channel
  * at least twitch_self_gap seconds between them
  * never right after my own message (no double texting)
  * never while chat is busy (people are already talking)
"""
import random


class SelfTalk:
    def __init__(self, config, clock, rng=random.random):
        self.c, self.clock, self.rng = config, clock, rng
        self.sent = {}                     # channel -> [timestamps of self-started messages]
        self.welcomed = set()              # (channel, user) welcomed this session

    def _recent(self, channel):
        cut = self.clock() - 3600
        self.sent[channel] = [t for t in self.sent.get(channel, []) if t >= cut]
        return self.sent[channel]

    def allowed(self, room) -> bool:
        c = self.c
        if not c.twitch_self_talk:
            return False
        sent = self._recent(room.channel)
        if len(sent) >= c.twitch_self_max_per_hour:
            return False
        if sent and self.clock() - sent[-1] < c.twitch_self_gap:
            return False
        if room.lines and room.lines[-1].is_bot:
            return False                   # don't double text
        return True

    def record(self, room):
        self._recent(room.channel).append(self.clock())

    def silence(self, room) -> bool:
        """Chat had a real conversation, then went quiet. Say one thing, once."""
        c = self.c
        if c.twitch_idle_sec <= 0 or room.idle_spoken or not room.lines:
            return False
        if room.quiet_for() < c.twitch_idle_sec:
            return False
        if room.human_count_since(c.twitch_idle_sec + 900) < 3:
            return False
        return self.allowed(room)

    def welcome(self, room, user, away, already_answering) -> bool:
        """A regular is back. Only if I'm not already replying to them, sometimes, once per session."""
        c = self.c
        if already_answering or away < c.twitch_welcome_back_sec:
            return False
        key = (room.channel, user)
        if key in self.welcomed:
            return False
        self.welcomed.add(key)             # decided once, whatever happens
        if room.human_count_since(30) > 6:  # chat is flying - nobody greets in that
            return False
        return self.rng() < c.twitch_welcome_chance and self.allowed(room)
