"""Chat rules - all plain logic, no network, so it's tested offline.

  * when to answer      (@mention, !winter, or a reply to the bot)
  * cooldowns           (per chatter + whole bot, so it never spams)
  * turning an answer into ONE Twitch chat line (no colors, threads or citations)
"""
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

URL = re.compile(r"(https?://\S+|www\.\S+|\b\S+\.(com|net|org|gg|tv|io|ly|me|xyz)\b\S*)", re.I)


@dataclass
class Incoming:
    channel: str            # broadcaster login
    channel_id: str
    user: str               # chatter login
    name: str               # chatter display name
    text: str
    message_id: str = ""
    reply_to_user: str = ""  # login of the person this message replies to
    mentions: List[str] = field(default_factory=list)


def parse_event(e: dict) -> Incoming:
    """EventSub channel.chat.message event -> Incoming."""
    msg = e.get("message") or {}
    mentions = [(f.get("mention") or {}).get("user_login", "").lower()
                for f in msg.get("fragments") or [] if f.get("type") == "mention"]
    reply = e.get("reply") or {}
    return Incoming(channel=e.get("broadcaster_user_login", ""), channel_id=e.get("broadcaster_user_id", ""),
                    user=(e.get("chatter_user_login") or "").lower(), name=e.get("chatter_user_name", ""),
                    text=msg.get("text", ""), message_id=e.get("message_id", ""),
                    reply_to_user=(reply.get("parent_user_login") or "").lower(), mentions=mentions)


def question_for_bot(m: Incoming, bot: str, prefix: str, ignore: List[str],
                     reply_all: bool = False) -> Optional[str]:
    """The text the bot should answer, or None if this message isn't for the bot.
    reply_all=True: chats like a normal viewer - answers every message,
    except ones aimed at someone else ("@otherguy lol")."""
    bot = bot.lower()
    if m.user == bot or m.user in {u.lower() for u in ignore}:
        return None
    text = m.text.strip()
    at = re.compile(rf"@{re.escape(bot)}\b[,:]?", re.I)
    if prefix and text.lower().split(" ")[0] == prefix.lower():
        q = text[len(prefix):]
    elif bot in m.mentions or at.search(text):
        q = text
    elif m.reply_to_user == bot:
        q = text
    elif reply_all and not m.reply_to_user and not (m.mentions or re.search(r"(^|\s)@\w", text)):
        q = text
    else:
        return None
    q = re.sub(r"\s+", " ", at.sub(" ", q)).strip()
    return q or "hey"


class Cooldown:
    def __init__(self, per_user: float, global_gap: float, clock=time.monotonic):
        self.per_user, self.gap, self.clock = per_user, global_gap, clock
        self.last_user, self.last_any = {}, -1e9

    def ready(self, user: str) -> bool:
        return self.clock() - self.last_user.get(user, -1e9) >= self.per_user

    def wait_global(self) -> float:
        return max(0.0, self.gap - (self.clock() - self.last_any))

    def mark(self, user: str):
        now = self.clock()
        self.last_user[user] = self.last_any = now


def chat_line(text: str, max_chars: int = 450, citations: bool = False,
              block_words: List[str] = ()) -> Optional[str]:
    """Winter's terminal answer -> one safe Twitch message (or None = don't send)."""
    text = (text or "").split("\n\n⏱️")[0]
    # keep the answer lines; drop citation / thread / "from my messages" lines (they start with spaces)
    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith((" ", "\t"))]
    s = " ".join(lines)
    s = s.replace("✨", "").replace("🤖", "")
    if not citations:
        s = re.sub(r"\s*\[\d+\]", "", s)
    s = URL.sub("", s)                                  # never post links
    s = re.sub(r"\s+", " ", s).strip().lstrip("/.!")    # can't trigger chat commands
    if not s:
        return None
    low = s.lower()
    for w in block_words:
        if re.search(rf"(?<![a-z]){re.escape(w.lower())}(?![a-z])", low):
            return None
    if len(s) > max_chars:
        cut = s[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        s = cut[:end + 1] if end > max_chars // 2 else cut.rsplit(" ", 1)[0] + "…"
    return s
