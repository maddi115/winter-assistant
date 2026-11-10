"""The bot's brain for Twitch.

  * sees the ROOM: the last few chat lines from everyone, so it knows what's going on
  * one conversation state per chatter (follow-ups like "anything else?" work per person)
  * nothing is saved to your own Winter history; strangers never see your private Winter chats
  * personality comes from memory/personality.md
"""
from collections import OrderedDict

from core import colors
from core.personality import load as load_personality
from twitch.rules import chat_line
from twitch.humanize import humanize

AI_ROUTES = {"general", "ai_no_evidence"}

IDLE_ASK = ("(chat went quiet. say ONE short casual thing to get it going again, about what people were "
            "just talking about. don't say hi, don't ask if anyone's there. if nothing fits, reply exactly: skip)")


class ChatterMemory:
    """Stands in for HybridRAG: only this chatter's own last turns."""

    def __init__(self, keep=0):
        self.turns, self.keep = [], keep

    def retrieve(self, query, storage, limit=None):
        return list(self.turns) if self.keep else []

    def add(self, user, assistant):
        if self.keep:
            self.turns = (self.turns + [{"user": user, "assistant": assistant}])[-self.keep:]


class Brain:
    def __init__(self, config, make_adapter, ai=None, base_context="", max_chatters=300):
        self.c = config
        self.make_adapter = make_adapter
        self.ai = ai
        self.base = base_context
        self.chatters = OrderedDict()
        self.max = max_chatters
        colors.ENABLED = False

    @property
    def personality(self):
        return load_personality(self.c.personality_file)

    def _adapter(self, user):
        if user in self.chatters:
            self.chatters.move_to_end(user)
            return self.chatters[user]
        mem = ChatterMemory(self.c.twitch_chat_memory)
        a = self.make_adapter(mem)
        a._save = lambda q, r, start, mem=mem: mem.add(q, r)    # never touches your LanceDB
        self.chatters[user] = a
        if len(self.chatters) > self.max:
            self.chatters.popitem(last=False)
        return a

    def _set_room(self, room, before=None, talking_to=None):
        """The chat AI gets the recent chat as background (one answer at a time, so this is safe)."""
        ctx = self.base
        if room is not None and room.lines:
            ctx += (f"\nRecent chat in #{room.channel} (oldest first, 'you' = your own messages):\n"
                    + room.as_text(self.c.twitch_room_lines, before))
        if talking_to:
            ctx += f"\nYou're answering {talking_to}. Don't repeat anything 'you' already said."
        self.c.chat_context = ctx

    def _polish(self, line, route):
        if line and self.c.twitch_humanize and route in AI_ROUTES:
            # the AI's own words only - Maddi's real quotes are never touched
            line = humanize(line, max_words=self.c.twitch_max_words, never=self.personality.never)
        return line or None

    def reply(self, user, name, question, room=None, line=None):
        """-> (chat line or None, route)"""
        a = self._adapter(user)
        is_owner = user in {h.lower() for h in self.c.owner_handles}
        key, data = a.router.route(question)
        if data and data.get("perspective") == "owner" and not is_owner:
            # "what's my name" from a stranger is about THEM, not Maddi
            line_ = f"ur {name} lol" if key == "USER_NAME" else "idk that one's on u lol"
            return line_, "stranger_self"
        self._set_room(room, before=line, talking_to=name)
        out = colors.strip("".join(a.chat(question)))
        text = chat_line(out, self.c.twitch_max_chars, self.c.twitch_citations,
                         self.c.twitch_block_words, self.c.twitch_max_quotes)
        return self._polish(text, a.last_route), a.last_route

    def break_silence(self, room):
        """Chat went quiet - one line based on what people were saying, or None."""
        if self.ai is None or not hasattr(self.ai, "generate"):
            return None
        self._set_room(room)
        try:
            raw = "".join(self.ai.generate(IDLE_ASK, []))
        except Exception:
            return None
        from transport.checker import persona_guard, claim_guard
        raw = claim_guard(persona_guard(raw, IDLE_ASK, self.c.persona_name) or "")
        if not raw or raw.strip(" .\"'").lower() == "skip" or "skip" == raw.strip().lower()[:4]:
            return None
        text = chat_line(raw, self.c.twitch_max_chars, False, self.c.twitch_block_words)
        return self._polish(text, "general")
