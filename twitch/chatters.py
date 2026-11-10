"""Remembers chatters between streams - like a regular would.

Saved to twitch_chatters.json (git-ignored, stays on your PC). Per chatter:
  first/last seen, how many messages, how often they talked with me,
  what they talk about (top words), and their last few lines.
Anyone can type !forgetme and they're wiped.
"""
import json
import time
from collections import Counter
from pathlib import Path

from retrieval.gradient import content_terms

KEEP_LINES = 5
KEEP_TOPICS = 8
MAX_CHATTERS = 2000
JUNK = {"lol", "lmao", "yo", "bro", "fr", "ngl", "tbh", "yeah", "nah", "ok", "okay", "haha", "lmfao",
        "omg", "bruh", "chat", "winter", "agentwinter", "agentwinterrr", "gonna", "wanna", "dont", "im",
        "anyone", "someone", "anybody", "everyone", "bet", "play", "playing", "got", "get", "just", "really",
        "think", "know", "want", "going", "back", "today", "tonight", "now", "here", "there", "thing", "stuff",
        "good", "nice", "cool", "true", "same", "what", "yall", "guys", "man", "dude", "lowkey", "deadass"}


def ago(seconds: float) -> str:
    s = int(seconds)
    if s < 3600:
        return f"{max(1, s // 60)} min"
    if s < 86400:
        return f"{s // 3600} hours"
    return f"{s // 86400} days"


class Chatters:
    def __init__(self, path=None, clock=time.time):
        self.path, self.clock = path, clock
        self.people = {}
        self.dirty = False
        if path and Path(path).exists():
            try:
                self.people = json.loads(Path(path).read_text())
            except Exception:
                self.people = {}

    def get(self, user):
        return self.people.get(user.lower())

    def seen(self, user, name, text, talked_to_me=False):
        """Call on every human message. Returns how long they were away (0 = new or just here)."""
        now, user = self.clock(), user.lower()
        p = self.people.get(user)
        away = 0.0
        if p is None:
            p = {"name": name, "first_seen": now, "last_seen": now, "messages": 0,
                 "talks": 0, "topics": {}, "lines": []}
            self.people[user] = p
        else:
            away = now - p["last_seen"]
        p["name"], p["last_seen"] = name or p["name"], now
        p["messages"] += 1
        if talked_to_me:
            p["talks"] += 1
        words = [w for w in content_terms(text) if w not in JUNK and len(w) > 2]
        topics = Counter(p["topics"])
        topics.update(words)
        p["topics"] = dict(topics.most_common(KEEP_TOPICS))
        p["lines"] = (p["lines"] + [text[:120]])[-KEEP_LINES:]
        self.dirty = True
        if len(self.people) > MAX_CHATTERS:          # forget whoever hasn't been around the longest
            oldest = min(self.people, key=lambda u: self.people[u]["last_seen"])
            self.people.pop(oldest, None)
        return away

    def forget(self, user):
        self.dirty = self.people.pop(user.lower(), None) is not None or self.dirty

    def note(self, user, away=0.0) -> str:
        """One short line for the AI: what a regular would remember about this person."""
        p = self.get(user)
        if not p or p["messages"] <= 1 and not away:
            return f"{p['name'] if p else user} is new in chat."
        bits = [f"{p['name']} has chatted {p['messages']} times (first seen {ago(self.clock() - p['first_seen'])} ago)"]
        if away >= 3600:
            bits.append(f"just came back after {ago(away)}")
        if p["topics"]:
            bits.append("they usually talk about: " + ", ".join(list(p["topics"])[:5]))
        return "; ".join(bits) + "."

    def save(self):
        if not (self.path and self.dirty):
            return
        tmp = Path(str(self.path) + ".tmp")
        tmp.write_text(json.dumps(self.people, indent=1))
        tmp.replace(self.path)                      # never leaves a half-written file
        self.dirty = False
