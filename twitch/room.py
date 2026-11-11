"""What's been said in chat lately - everyone's messages, not just ones to the bot."""
import re
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class Line:
    user: str
    name: str
    text: str
    ts: float
    is_bot: bool = False
    vec: object = None       # meaning vector, computed once (saves GPU/CPU)


class Room:
    def __init__(self, channel, keep=50, clock=time.time, guest=False):
        self.channel, self.clock, self.guest = channel, clock, guest
        self.drops = 0                  # Twitch dropped my messages in a row (slow mode, AutoMod...)
        self.muted_until = 0.0          # too many drops -> stop sending here for a while
        self.lines = deque(maxlen=keep)
        self.times = deque(maxlen=1000)  # when humans talked - for chat speed (more than the 50 lines kept)
        self.last_bot = -1e9            # when the bot last spoke
        self.last_chime = -1e9          # when the bot last jumped in uninvited
        self.last_meow = -1e9           # meows have their own timer (don't eat the join-in budget)
        self.last_wave = -1e9           # when I last joined a chat wave
        self.last_considered = -1e9     # a moment I thought about but stayed quiet on (short pause)
        self.stream = ""                # "title · category" from Twitch, so I know what's on screen
        self.heard = None               # Transcript of what the streamer just said (if listening)
        self.emote_times = []           # my emote reactions (their own budget)
        self.last_emote = None
        self.uninvited = []             # times I spoke without being asked (budget)
        self.used_quotes = set()        # my real messages already said here this stream (no repeats)
        self.sub_emotes = set()         # the streamer's sub emotes - I can't post them
        self.emote_seen = {}            # emote -> [(time, user)] for emotes I could post
        self.native = set()             # Twitch-marked global emotes seen here (they render for everyone)
        self.native_only = True         # only post emotes that show as a picture without BTTV/7TV
        self.mine = set()               # emotes MY account can post here (from Twitch), empty = not loaded
        self.idle_spoken = False        # already broke one silence since the last human message

    def add(self, user, name, text, is_bot=False) -> Line:
        line = Line(user, name, text, self.clock(), is_bot)
        self.lines.append(line)
        if is_bot:
            self.last_bot = line.ts
        else:
            self.idle_spoken = False
            self.times.append(line.ts)
        return line

    def recent(self, n=12, before: Line = None):
        lines = list(self.lines)
        if before is not None and before in lines:
            lines = lines[:lines.index(before)]
        return lines[-n:]

    def humans_since(self, seconds):
        cut = self.clock() - seconds
        return {l.user for l in self.lines if not l.is_bot and l.ts >= cut}

    def human_count_since(self, seconds):
        cut = self.clock() - seconds
        return sum(1 for l in self.lines if not l.is_bot and l.ts >= cut)

    def quiet_for(self):
        return self.clock() - self.lines[-1].ts if self.lines else 0.0

    def as_text(self, n=12, before: Line = None, bot_label="you") -> str:
        out = []
        for l in self.recent(n, before):
            who = bot_label if l.is_bot else l.name
            t = l.text if len(l.text) <= 150 else l.text[:147] + "..."
            out.append(f"{who}: {t}")
        return "\n".join(out)

    def bot_lines(self, n=5):
        return [l.text for l in self.lines if l.is_bot][-n:]

    def mpm(self, window=60):
        """Chat speed: human messages per minute lately."""
        cut = self.clock() - window
        return sum(1 for t in self.times if t >= cut) * 60.0 / window

    def spoke_uninvited(self):
        self.uninvited.append(self.clock())
        self.last_chime = self.clock()

    def uninvited_since(self, seconds):
        cut = self.clock() - seconds
        self.uninvited = [t for t in self.uninvited if t >= cut]
        return len(self.uninvited)

    def wave(self, seconds=15, people=4):
        """Several people spamming the same kind of reaction right now -> its mood, else None."""
        from twitch.emotes import is_reaction, mood
        cut = self.clock() - seconds
        recent = [l for l in self.lines if not l.is_bot and l.ts >= cut and is_reaction(l.text)]
        moods = {}
        for l in recent:
            moods.setdefault(mood(l.text), set()).add(l.user)
        best = max(((m, len(u)) for m, u in moods.items() if m != "other"), key=lambda x: x[1], default=None)
        return best[0] if best and best[1] >= people else None

    def note_emotes(self, user, text, marked=(), plain=None):
        """Learn which emotes this chat uses. Twitch-marked: global ones are fine, sub emotes aren't.
        Unmarked emote-looking words (BTTV/7TV like ICANT, KEKW) count once 2+ people use them."""
        from twitch.emotes import TOKEN, MEANING, _CANON, looks_like_emote
        now = self.clock()
        for e in marked or ():
            name = e.get("name", "")
            if e.get("owner") in ("", "0") or e.get("set") == "0" or name in self.mine:
                self.emote_seen.setdefault(name, []).append((now, user))
                self.native.add(name)
            else:
                self.sub_emotes.add(name)
        src = plain if plain is not None else text
        tagged = {w.lower() for w in re.findall(r"@(\w+)", src)}
        users = {l.user.lower() for l in self.lines} | tagged
        words = TOKEN.findall(re.sub(r"@\w+", " ", src))
        for w in words:
            if w in self.sub_emotes or w.lower() in users:
                continue                # "RichieFlair" is a person, not an emote
            # known emotes, or mixed-case emote names (catJAM) - not ALL CAPS words like WILD / HUH
            if w.lower() in _CANON or (looks_like_emote(w) and not w.islower() and not w.isupper()):
                self.emote_seen.setdefault(w, []).append((now, user))

    def renders(self, name):
        """Will this show as a picture for everyone? (Twitch global, not a BTTV/7TV word)"""
        from twitch.emotes import TWITCH_GLOBAL
        if not self.native_only or name in self.native or name in self.mine:
            return True
        return not self.mine and name in TWITCH_GLOBAL      # Twitch list not loaded -> built-in fallback

    def usable_emotes(self, window=1800, people=2, top=8):
        """Emotes I can use here: seen from 2+ people lately, never sub emotes, and (by default)
        only ones that render for everyone - else chat just sees the word 'ICANT'."""
        cut = self.clock() - window
        ranked = []
        for name, uses in self.emote_seen.items():
            uses[:] = [u for u in uses if u[0] >= cut]
            who = {u for _, u in uses}
            if name not in self.sub_emotes and len(who) >= people and self.renders(name):
                ranked.append((len(uses), name))
        return [n for _, n in sorted(ranked, reverse=True)[:top]]

    def wave_emote(self, seconds=15):
        """The emote the wave itself is using (if I can post it) - join with the room's own emote."""
        from collections import Counter
        from twitch.emotes import TOKEN
        cut = self.clock() - seconds
        usable = set(self.usable_emotes(window=seconds + 60, people=2))
        count = Counter(w for l in self.lines if not l.is_bot and l.ts >= cut
                        for w in set(TOKEN.findall(l.text)) if w in usable)
        best = count.most_common(1)
        return best[0][0] if best and best[0][1] >= 2 else None
