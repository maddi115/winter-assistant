#!/usr/bin/env python
"""Twitch bot tests - no Twitch, no Ollama, no GPU.   python tests/test_twitch_offline.py"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from twitch import rules, brain as brain_mod, auth, eventsub
from twitch.rules import Incoming, parse_event, question_for_bot, Cooldown, chat_line
from twitch.http import HTTPError

FAILS = []


def check(name, cond, info=""):
    print(("  ✅ " if cond else "  ❌ ") + name + ("" if cond else f"   -> {info}"))
    if not cond:
        FAILS.append(name)


def msg(text, user="viewer1", reply_to="", mentions=()):
    return Incoming("chan", "1", user, user.title(), text, "m1", reply_to, list(mentions))


IGN = ["nightbot"]

print("\nA. When does the bot answer?")
check("@mention -> answers, mention removed",
      question_for_bot(msg("@agentWinter do you like burritos?", mentions=["agentwinter"]), "agentwinter", "!winter", IGN)
      == "do you like burritos?")
check("mention in the middle", question_for_bot(msg("yo @agentwinter, u like soda"), "agentwinter", "!winter", IGN) == "yo u like soda")
check("!winter prefix", question_for_bot(msg("!winter do you like kombucha"), "agentwinter", "!winter", IGN) == "do you like kombucha")
check("!winterfoo is NOT the prefix", question_for_bot(msg("!winterfoo hi"), "agentwinter", "!winter", IGN) is None)
check("reply to the bot", question_for_bot(msg("@agentwinter anything else?", reply_to="agentwinter"), "agentwinter", "!winter", IGN) == "anything else?")
check("normal chat ignored", question_for_bot(msg("lol this stream"), "agentwinter", "!winter", IGN) is None)
check("other people's mentions ignored", question_for_bot(msg("@someone do you like burritos"), "agentwinter", "!winter", IGN) is None)
check("never answers itself", question_for_bot(msg("@agentwinter hi", user="agentwinter"), "agentwinter", "!winter", IGN) is None)
check("ignores other bots", question_for_bot(msg("!winter hi", user="nightbot"), "agentwinter", "!winter", IGN) is None)
check("bare @mention -> 'hey'", question_for_bot(msg("@agentwinter"), "agentwinter", "!winter", IGN) == "hey")
check("@agentwinterfan is not the bot", question_for_bot(msg("@agentwinterfan hi"), "agentwinter", "!winter", IGN) is None)

check("chat-like mode: answers a normal message", question_for_bot(msg("do you like burritos"), "agentwinter", "!winter", IGN, True) == "do you like burritos")
check("chat-like mode: skips messages aimed at someone else", question_for_bot(msg("@someone lol"), "agentwinter", "!winter", IGN, True) is None)
check("chat-like mode: skips replies to other people", question_for_bot(msg("true", reply_to="someone"), "agentwinter", "!winter", IGN, True) is None)
check("chat-like mode: still ignores itself + bots",
      question_for_bot(msg("hi", user="agentwinter"), "agentwinter", "!winter", IGN, True) is None
      and question_for_bot(msg("hi", user="nightbot"), "agentwinter", "!winter", IGN, True) is None)
check("chat-like mode: @bot still works", question_for_bot(msg("@agentwinter yo", mentions=["agentwinter"]), "agentwinter", "!winter", IGN, True) == "yo")

print("\nB. Parsing a real EventSub event")
ev = {"broadcaster_user_id": "123", "broadcaster_user_login": "chan", "chatter_user_id": "9",
      "chatter_user_login": "Viewer1", "chatter_user_name": "Viewer1", "message_id": "abc",
      "message": {"text": "@agentwinter hi", "fragments": [
          {"type": "mention", "text": "@agentwinter", "mention": {"user_id": "5", "user_login": "agentwinter", "user_name": "agentWinter"}},
          {"type": "text", "text": " hi"}]},
      "reply": None}
m = parse_event(ev)
check("fields", (m.channel, m.channel_id, m.user, m.message_id) == ("chan", "123", "viewer1", "abc"), m)
check("mention fragments", m.mentions == ["agentwinter"], m.mentions)
ev2 = dict(ev, reply={"parent_user_login": "agentwinter", "parent_message_id": "x"})
check("reply parent", parse_event(ev2).reply_to_user == "agentwinter")

print("\nC. Cooldowns")
t = [100.0]
cd = Cooldown(20, 3, clock=lambda: t[0])
check("first ask ready", cd.ready("a"))
cd.mark("a")
t[0] = 110
check("same chatter waits", not cd.ready("a"))
check("other chatter fine", cd.ready("b"))
check("global gap already passed", cd.wait_global() == 0)
cd.mark("b"); t[0] = 111
check("global gap waits ~2s", abs(cd.wait_global() - 2) < 1e-9, cd.wait_global())
t[0] = 131
check("cooldown ends", cd.ready("a"))

print("\nD. One clean chat line")
term = ("For sure. I like eating burritos [1] I love burrito de birria [2]\n"
        "   [2] twitch · 2025-07-20\n   🧵 [1] twitch · 2025-07-05 17:59\n      Of course with rice.\n"
        "    → I like eating burritos\n\n⏱️  1.20s · algo\n")
check("drops citations, threads, timer", chat_line(term) == "For sure. I like eating burritos I love burrito de birria", chat_line(term))
check("citations kept if asked", "[1]" in chat_line(term, citations=True))
synth = "✨ I usually eat chips or cheetos with it [1][2]\n   ↳ from my messages: chips [1] cheetos [2]\n"
check("synthesis -> just the sentence", chat_line(synth) == "I usually eat chips or cheetos with it", chat_line(synth))
check("general chat paragraphs joined", chat_line("hey lol\nwhats good") == "hey lol whats good")
check("no links", chat_line("check https://evil.com and evil.gg/x now") == "check and now", chat_line("check https://evil.com and evil.gg/x now"))
check("can't run /commands", chat_line("/ban someone") == "ban someone")
check("blocked words -> nothing sent", chat_line("just kys lol", block_words=["kys"]) is None)
check("blocked word inside another word is fine", chat_line("skyscraper", block_words=["kys"]) == "skyscraper")
long = "this is a sentence. " * 40
out = chat_line(long, 450)
check("long -> cut at sentence, <=450", len(out) <= 450 and out.endswith("."), (len(out), out[-10:]))
check("empty -> None", chat_line("   \n\n⏱️ 1s") is None)

print("\nE. Brain: one conversation per chatter, nothing saved to your history")


class FakeRouter:
    def route(self, q):
        if q == "whats my name":
            return "USER_NAME", {"value": "Maddi", "perspective": "owner"}
        return None, None


class FakeAdapter:
    made = []

    def __init__(self, mem):
        self.mem, self.router, self.last_route = mem, FakeRouter(), None
        self.saved_to_db = False
        FakeAdapter.made.append(self)

    def _save(self, *a):
        self.saved_to_db = True

    def chat(self, q):
        seen = len(self.mem.turns)
        self._save(q, "ok", 0)
        self.last_route = "general"
        yield f"\x1b[38;2;1;2;3mreply to {q} (seen {seen})\x1b[0m"
        yield "\n\n⏱️  0.1s · general\n"


cfg = Config()
cfg.owner_handles = ["madddyyyyi"]
b = brain_mod.Brain(cfg, FakeAdapter, max_chatters=2)
line, route = b.reply("viewer1", "Viewer1", "hi")
check("colors stripped, timer gone", line == "reply to hi (seen 0)", line)
line, _ = b.reply("viewer1", "Viewer1", "anything else?")
check("same chatter remembers their turns", line.endswith("(seen 1)"), line)
line, _ = b.reply("viewer2", "Viewer2", "hi")
check("other chatter starts fresh", line.endswith("(seen 0)"), line)
check("nothing saved to LanceDB", not any(a.saved_to_db for a in FakeAdapter.made))
line, route = b.reply("viewer3", "Viewer3", "whats my name")
check("stranger 'whats my name' -> their name, not Maddi", line == "ur Viewer3 lol" and route == "stranger_self", line)
check("old chatters dropped past the limit", len(b.chatters) == 2 and "viewer1" not in b.chatters)
line, route = b.reply("madddyyyyi", "madddyyyyi", "whats my name")
check("the owner still gets the real answer", route == "general", route)

print("\nE2. Sounds like a person, not a bot")
from twitch.humanize import humanize
from core.reflexes import reflex
check("'hey bro! what's up? 🫡' -> 'hey bro'", humanize("hey bro! what's up? 🫡") == "hey bro", humanize("hey bro! what's up? 🫡"))
check("no emoji, no '!', lowercase", humanize("Lol cute, did a cat just speak to you? 😹") == "lol cute, did a cat just speak to you?",
      humanize("Lol cute, did a cat just speak to you? 😹"))
check("no assistant opener", humanize("Hello there! Pizza is great.") == "hey pizza is great", humanize("Hello there! Pizza is great."))
check("drops trailing period", humanize("nah not really.") == "nah not really")
check("never empties a reply", humanize("what's up?") != "")
for m in ["meow", "MEOW", "meowww", "meow meow", "mrow", "  meow!  ", "nyaa"]:
    check(f"'{m}' -> meow back", (reflex(m) or "").startswith("meow"), reflex(m))
check("'meow baow' is one of them", "meow baow" in __import__("core.reflexes", fromlist=["x"]).MEOW_BACK)
check("normal text isn't a meow", reflex("homeowner") is None and reflex("meow is my cat's name") is None)
c2 = Config(); c2.owner_handles = []


class QuoteAdapter(FakeAdapter):
    def chat(self, q):
        self.last_route = "algo"
        yield "For sure. I LOVE burritos! [1]\n   [1] twitch\n"


bq = brain_mod.Brain(c2, QuoteAdapter)
check("Maddi's real quotes are NOT humanized", bq.reply("v", "V", "do you like burritos")[0] == "For sure. I LOVE burritos!")
bg = brain_mod.Brain(c2, FakeAdapter)
check("AI chat lines ARE humanized", bg.reply("v", "V", "Hi")[0] == "reply to hi (seen 0)")

print("\nF. Login (device code flow, faked)")
calls = []


def fake_request(method, url, headers=None, form=None, body=None, timeout=15):
    calls.append(url)
    if url == auth.DEVICE_URL:
        return 200, {"device_code": "dc", "user_code": "ABCD", "verification_uri": "https://www.twitch.tv/activate",
                     "expires_in": 600, "interval": 0}
    if url == auth.TOKEN_URL:
        if calls.count(auth.TOKEN_URL) == 1:
            raise HTTPError(400, {"message": "authorization_pending"})
        return 200, {"access_token": "AT", "refresh_token": "RT"}
    if url == auth.VALIDATE_URL:
        return 200, {"login": "agentwinter", "user_id": "55", "scopes": auth.SCOPES.split()}


auth.request = fake_request
auth.time.sleep = lambda s: None
path = Path(tempfile.mkdtemp()) / "tok.json"
import contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
    tok = auth.device_login("cid", path)
saved = json.loads(path.read_text())
check("waits while pending, then saves token", saved["access_token"] == "AT" and saved["login"] == "agentwinter", saved)
check("token file is private (600)", oct(path.stat().st_mode)[-3:] == "600", oct(path.stat().st_mode))
T = auth.Token("cid", path)
check("Token loads + validates", (T.login, T.user_id, T.access) == ("agentwinter", "55", "AT"))

print("\nG. EventSub against a fake Twitch server (welcome -> chat -> reconnect -> chat)")


async def eventsub_test():
    from websockets.asyncio.server import serve
    got, subs, conns = [], [], []

    def note(kind, ev=None):
        d = {"metadata": {"message_type": kind, "subscription_type": "channel.chat.message"}, "payload": {}}
        if kind == "session_welcome":
            d["payload"] = {"session": {"id": f"s{len(conns) - 1}", "keepalive_timeout_seconds": 10}}
        if kind == "notification":
            d["payload"] = {"event": ev}
        if kind == "session_reconnect":
            d["payload"] = {"session": {"reconnect_url": f"ws://127.0.0.1:{port}/re"}}
        return json.dumps(d)

    async def handler(ws):
        conns.append(ws.request.path)
        await ws.send(note("session_welcome"))
        if ws.request.path == "/re":
            await ws.send(note("notification", {"message": {"text": "second"}}))
        else:
            await ws.send(note("session_keepalive"))
            await ws.send(note("notification", {"message": {"text": "first"}}))
            await ws.send(note("session_reconnect"))
        await asyncio.sleep(5)

    class FakeHelix:
        def subscribe_chat(self, sid, cid, bid):
            subs.append((sid, cid, bid))

    async def on_event(e):
        got.append(e["message"]["text"])

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        eventsub.EVENTSUB_URL = f"ws://127.0.0.1:{port}/ws"
        task = asyncio.create_task(eventsub.listen(FakeHelix(), "55", {"chan": "1"}, on_event, log=lambda s: None))
        for _ in range(50):
            await asyncio.sleep(0.05)
            if len(got) >= 2:
                break
        task.cancel()
    return got, subs, conns


got, subs, conns = asyncio.run(eventsub_test())
check("got chat before and after reconnect", got == ["first", "second"], got)
check("subscribed once (reconnect keeps subscriptions)", subs == [("s0", "1", "55")], subs)
check("followed Twitch's reconnect url", conns == ["/ws", "/re"], conns)

print("\nH. Config")
c = Config()
check("defaults: prefix, cooldowns, 450 chars", (c.twitch_prefix, c.twitch_user_cooldown, c.twitch_max_chars) == ("!winter", 4, 450))
check("no reply threads by default (normal chatter)", c.twitch_reply_thread is False)
check("token file is git-ignored", "twitch_token.json" in (Path(__file__).resolve().parent.parent / ".gitignore").read_text())
from core.ai_engine import persona_prompt
c.chat_context = "TWITCH LINE"
check("chat_context reaches the chat AI prompt", persona_prompt(c, "").endswith("TWITCH LINE"))
c.chat_context = ""
check("terminal prompt unchanged", "TWITCH" not in persona_prompt(c, ""))

print(f"\n{'❌ ' + str(len(FAILS)) + ' failed: ' + ', '.join(FAILS) if FAILS else '✅ all twitch tests passed'}")
sys.exit(1 if FAILS else 0)
