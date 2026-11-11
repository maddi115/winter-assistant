"""What's been said in chat lately - everyone's messages, not just ones to the bot."""
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
        self.uninvited = []             # times I spoke without being asked (budget)
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
