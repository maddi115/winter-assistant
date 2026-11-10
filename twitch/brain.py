"""One conversation per chatter, nothing saved to your own Winter history.

Each chatter gets their own short memory (last few turns), so follow-ups
("anything else?") work per person and strangers never see your private Winter chats.
"""
from collections import OrderedDict

from core import colors
from twitch.rules import chat_line


class ChatterMemory:
    """Stands in for HybridRAG: only this chatter's own last turns."""

    def __init__(self, keep=4):
        self.turns, self.keep = [], keep

    def retrieve(self, query, storage, limit=None):
        return list(self.turns)

    def add(self, user, assistant):
        self.turns = (self.turns + [{"user": user, "assistant": assistant}])[-self.keep:]


class Brain:
    def __init__(self, config, make_adapter, max_chatters=300):
        self.c = config
        self.make_adapter = make_adapter
        self.chatters = OrderedDict()
        self.max = max_chatters
        colors.ENABLED = False

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

    def reply(self, user, name, question):
        """-> (chat line or None, route)"""
        a = self._adapter(user)
        is_owner = user in {h.lower() for h in self.c.owner_handles}
        key, data = a.router.route(question)
        if data and data.get("perspective") == "owner" and not is_owner:
            # "what's my name" from a stranger is about THEM, not Maddi
            line = f"ur {name} lol" if key == "USER_NAME" else "idk that one's on u lol"
            return line, "stranger_self"
        out = colors.strip("".join(a.chat(question)))
        line = chat_line(out, self.c.twitch_max_chars, self.c.twitch_citations, self.c.twitch_block_words)
        return line, a.last_route
