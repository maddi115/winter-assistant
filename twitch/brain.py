"""The bot's brain for Twitch.

  * sees the ROOM: the last few chat lines from everyone, so it knows what's going on
  * one conversation state per chatter (follow-ups like "anything else?" work per person)
  * nothing is saved to your own Winter history; strangers never see your private Winter chats
  * personality comes from memory/personality.md
"""
import json
import re
import threading
from collections import OrderedDict

from core import colors
from core.personality import load as load_personality
from twitch.rules import chat_line
from twitch.humanize import humanize

AI_ROUTES = {"general", "ai_no_evidence"}
QUOTE_ROUTES = {"algo", "ai_pick", "ai_synth", "algo_fallback"}
ABOUT_ME = re.compile(
    r"\b(do|did|have|are|were|would|will|can|could|should)\s+(you|u)\b(?!\s+(think|thin|know|guys|see|hear|mean|"
    r"remember|believe|reckon))|\b(your|ur)\s+(fav|favorite|favourite|"
    r"opinion|take|go-?to)\b|\bwhat\s+(do|did)\s+(you|u)\s+(like|love|hate|think|eat|drink|play|watch|do)\b|"
    r"\bhave\s+(you|u)\s+ever\b|\b(you|u)\s+(like|love|hate|play|watch|eat|drink)\b", re.I)


def asks_about_me(q) -> bool:
    """'do u like burritos' / 'whats ur fav food' = about me. 'how does sam smell' = not."""
    return bool(ABOUT_ME.search(q or ""))
# who-am-i questions in public chat: just my name. AI only when sincerely asked. Tech details stay private.
PUBLIC_FACTS = {
    "AI_NAME": "{name}. u?",
    "AI_DISCLOSURE": "yeah its an ai account",
    "AI_OWNER": "thats private 🙏",
    "AI_MODEL": "thats private 🙏",
    "AI_STORAGE": "thats private 🙏",
    "AI_EMBEDDING": "thats private 🙏",
}

SELF_ASK = {
    "silence": ("(chat went quiet. say ONE short casual thing to get it going again, about what people were "
                "just talking about. don't say hi, don't ask if anyone's there. if nothing fits, reply exactly: skip)"),
    # joining in on chat I wasn't asked into: the AI decides if it actually has something good
    "chime": ("(you're reading chat, nobody asked you anything. the newest message is from {name}: "
              "\"{text}\". only if you have something genuinely good to add - funny, relatable, or a real "
              "answer to what people are talking about - write ONE short message like a regular would. "
              "don't greet anyone, don't ask what's up, don't change the subject. "
              "if you'd just be filling space, reply exactly: skip)"),
    "welcome": ("({name} just came back to chat. {note} say a quick casual hi to them by name, like a friend, "
                "a few words. only mention what they usually talk about if it fits naturally. "
                "if it'd be weird, reply exactly: skip)"),
}


def backed_by(line, fact, need=2) -> bool:
    """The line's real words come from my real message (at least `need` of them)."""
    from retrieval.gradient import content_terms, stem
    mine = {stem(w) for w in content_terms(fact)}
    said = {stem(w) for w in content_terms(line)}
    return len(mine & said) >= need


def is_skip(text) -> bool:
    return re.sub(r"[^a-z]", "", (text or "").lower())[:4] == "skip" and len((text or "").split()) <= 3


def repeats(line, previous, limit=0.6) -> bool:
    """True if this line is (nearly) something I already said."""
    words = set(re.findall(r"[a-z0-9']+", line.lower()))
    for p in previous:
        other = set(re.findall(r"[a-z0-9']+", p.lower()))
        if words and other and len(words & other) / len(words | other) >= limit:
            return True
    return False


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
        self.last_context = ""
        self.gpu = threading.Lock()          # one search / answer at a time on the GPU
        self._known = OrderedDict()          # text -> my real message about it (or None)
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

    def topic(self, text, room=None, line=None):
        """Is chat having one real conversation around this message? (Twitch chat only, never my data)
        Builds the numbered chat lines + runs the stasis gate. Cached for speak_up."""
        from twitch import chatflow as F
        if room is None:
            return False
        line = line or next((l for l in reversed(room.lines) if l.text == text and not l.is_bot), None)
        if line is None:
            return False
        key = (room.channel, line.ts, line.user)
        if key in self._known:
            return self._known[key][0]
        embed = getattr(getattr(self._transport(), "searcher", None), "embedder", None)
        try:
            with self.gpu:
                lines, sims, vecs = F.thread(room, line, embed)
            ok, why = F.one_conversation(lines, sims, vecs, self.c, F.room_names(room))
        except Exception as e:
            lines, ok, why = [line], False, f"error: {e}"
        self._known[key] = (ok, lines, why)
        if len(self._known) > 500:
            self._known.popitem(last=False)
        return ok

    knows = topic                            # old name

    def _transport(self):
        a = next(iter(self.chatters.values()), None) or self.make_adapter(ChatterMemory(0))
        return getattr(a, "transport", None)

    def _set_room(self, room, before=None, talking_to=None, note=None, may_skip=False, current="", fact=None):
        """The chat AI gets the recent chat + what I remember about this person
        as background (one answer at a time, so this is safe)."""
        ctx = self.base
        recent = self._pertinent(room, before) if room is not None else ""
        if recent:
            ctx += (f"\nRecent chat in #{room.channel} (oldest first, 'you' = your own messages):\n" + recent)
        if room is not None and getattr(room, "stream", ""):
            ctx += f"\nOn stream right now: {room.stream}"
        if talking_to:
            ctx += f"\nYou're answering {talking_to}. Don't repeat anything 'you' already said."
        if note:
            ctx += f"\nWhat you remember about them (don't recite it, just know it): {note}"
        ctx += ("\nOnly say someone is 'back' or that you 'missed' them if the notes say they came back. "
                "Don't copy lines from the chat above.")
        from twitch.emotes import cheat_sheet
        lines = [l.text for l in room.recent(self.c.twitch_room_lines)] if room is not None else []
        sheet = cheat_sheet(lines + [current])
        if sheet:
            ctx += f"\nTwitch emotes in chat are reactions, not words: {sheet}."
        room_emotes = room.usable_emotes() if room is not None and hasattr(room, "usable_emotes") else []
        if room_emotes:
            ctx += (f"\nEmotes people use in this chat (you may use ONE if it really fits, most messages none): "
                    + " ".join(room_emotes[:6]))
        if before is not None:
            ctx += f"\nYou're reacting to {before.name}: \"{before.text[:150]}\""
        if fact:
            ctx += (f"\nSomething you REALLY said before about this (use it in your own words only if it fits, "
                    f"never quote it, don't add details): \"{fact}\"")
        if may_skip:
            ctx += ("\nNot every message needs an answer. If this one doesn't (filler, a random word, "
                    "nothing to add), reply exactly: skip")
        self.c.chat_context = ctx
        self.last_context = ctx[len(self.base):].strip()   # what the AI saw (for --show-context)

    def _pertinent(self, room, before=None, n=10):
        """Chat for the AI: real talk only (no reactions, emote spam or touchy lines), newest n."""
        from twitch import chatflow as F
        avoid = getattr(self.c, "twitch_avoid_topics", [])
        keep = [l for l in room.recent(self.c.twitch_room_lines * 2, before)
                if l.is_bot or (not F.touchy([l], avoid) and l in F.clean_lines(room, before, 60))][-n:]
        out = []
        for l in keep:
            t = l.text if len(l.text) <= 150 else l.text[:147] + "..."
            out.append(f"{'you' if l.is_bot else l.name}: {t}")
        return "\n".join(out)

    def _polish(self, line, route, room=None):
        guest = getattr(room, "guest", False)
        if line and self.c.twitch_humanize and route in AI_ROUTES:
            # the AI's own words only - Maddi's real quotes are never touched
            words = self.c.twitch_guest_max_words if guest else self.c.twitch_max_words
            allowed = list(self.personality.emojis) + (room.usable_emotes() if hasattr(room, "usable_emotes") else [])
            line = humanize(line, max_words=words, never=self.personality.never, emojis=allowed)
        if line and is_skip(line):
            return None                      # the AI decided this didn't need an answer
        if line and re.search(rf"\b{re.escape(self.c.persona_name.lower())}\b", line.lower()):
            return None                      # never name the owner in chat
        if line and room is not None and repeats(line, room.bot_lines(5)):
            return None                      # saying the same thing twice reads like a bot
        return line or None

    def reply(self, user, name, question, room=None, line=None, note=None, may_skip=False):
        """-> (chat line or None, route)"""
        a = self._adapter(user)
        is_owner = user in {h.lower() for h in self.c.owner_handles}
        public = getattr(self.c, "public_persona", False)
        if public:
            from twitch import chatflow as F
            if F.touchy([type("L", (), {"text": question})()], getattr(self.c, "twitch_avoid_topics", [])):
                return "nah im good 🙏", "dodge"            # bait about race, sex, drugs... -> no
        a.skip_transport = public and not asks_about_me(question)   # "how does sam smell" isn't about me
        key, data = a.router.route(question)
        if key in PUBLIC_FACTS and public:
            return PUBLIC_FACTS[key].format(name=self.c.agent_label), "fact"
        if data and data.get("perspective") == "owner" and not is_owner:
            # "what's my name" from a stranger is about THEM, not Maddi
            line_ = f"ur {name} lol" if key == "USER_NAME" else "idk that one's on u lol"
            return line_, "stranger_self"
        self._set_room(room, before=line, talking_to=name, note=note, may_skip=may_skip, current=question)
        with self.gpu:
            out = colors.strip("".join(a.chat(question)))
        guest = getattr(room, "guest", False)
        limit = self.c.twitch_guest_quote_chars if guest and a.last_route not in AI_ROUTES else self.c.twitch_max_chars
        text = chat_line(out, limit, self.c.twitch_citations, self.c.twitch_block_words, self.c.twitch_max_quotes)
        if text and a.last_route in QUOTE_ROUTES and len(text.split()) < self.c.twitch_quote_min_words:
            return None, a.last_route            # "For real, I thin." - a scrap, not an answer
        return self._polish(text, a.last_route, room), a.last_route

    def self_line(self, room, kind="silence", name=None, note=None, text=None, fact=None):
        """Talking without being asked: silence / welcome (self_talk.py) or chime (talk.py).
        -> one line, or None when the AI has nothing good to say."""
        self._set_room(room, current=text or "", fact=fact)   # first, so --show-context is never stale
        if self.ai is None or not hasattr(self.ai, "generate"):
            return None
        ask = SELF_ASK[kind].format(name=name or "someone", note=note or "", text=(text or "")[:200])
        try:
            with self.gpu:
                raw = "".join(self.ai.generate(ask, []))
        except Exception:
            return None
        from transport.checker import persona_guard, claim_guard
        raw = persona_guard(raw, ask, self.c.persona_name) or ""
        guarded = claim_guard(raw)
        if not guarded and fact and backed_by(raw, fact):
            guarded = raw                    # a claim about me is fine when my real message backs it
        raw = guarded
        if not raw or is_skip(raw):
            return None
        line = chat_line(raw, self.c.twitch_max_chars, False, self.c.twitch_block_words)
        return self._polish(line, "general", room)

    def speak_up(self, room, line, name=None):
        """A moment happened. Same architecture as answering about me, but the source of truth is
        THIS chat: numbered chat lines -> AI picks lines + reaction -> one line -> checks. Else silence.
        -> (line or None, route)"""
        from twitch import chatflow as F
        key = (room.channel, line.ts, line.user)
        if not self.topic(line.text, room, line):
            why = self._known.get(key, (0, 0, "not one conversation"))[2]
            self.last_context = f"stayed quiet: {why}"
            return None, why
        _, lines, _ = self._known[key]
        llm = getattr(self._transport(), "llm", None)
        if llm is None:
            self.last_context = "chat lines:\n" + F.numbered(lines)
            return None, "no AI to pick"
        stream = getattr(room, "stream", "")
        msgs = F.pick_messages(lines, stream)
        with self.gpu:
            react, picked, votes = F.pick(llm, msgs, len(lines), self.c.twitch_picker_votes,
                                          max_lines=self.c.twitch_pick_max_lines)
        self.last_context = F.numbered(lines) + f"\nvotes: {votes} -> {react} {picked}"
        if react == "skip":
            return None, "skip (votes)"
        chosen = [lines[i - 1] for i in picked]
        from core.style import load as load_style
        style = load_style(self.c.style_file) or self.c.style_words
        try:
            with self.gpu:
                raw = json.loads(llm.chat_json(F.write_messages(style + "\n" + self.personality.prompt, chosen, react,
                                                                stream),
                                               F.LINE_SCHEMA, max_tokens=40, temperature=0.7)).get("line", "")
        except Exception:
            raw = ""
        self.last_context += f"\nwrote: {raw!r}"
        text = chat_line(raw, self.c.twitch_max_chars, False, self.c.twitch_block_words)
        if not text:
            return None, "nothing written"
        from transport.checker import claim_guard
        slang = set(re.findall(r"[a-z']+", style.lower()))
        if not F.grounded(text, chosen, slang):
            return None, "made something up (word check)"
        if not F.specific(text, chosen, F.room_names(room)):
            return None, "too generic (doesn't name the thing)"
        if F.about_me(text) or not claim_guard(text):
            return None, "talked about itself"
        text = self._polish(text, "general", room)
        if not text:
            return None, "didn't pass the filters"
        if self.c.twitch_sense_check:
            with self.gpu:
                ok = F.makes_sense(llm, chosen, text, stream=stream)
            self.last_context += f"\nmakes sense: {ok}"
            if not ok:
                return None, "didn't make sense (votes)"
        return text, "from chat"

    def break_silence(self, room):
        return self.self_line(room, "silence")
