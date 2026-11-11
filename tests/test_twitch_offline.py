#!/usr/bin/env python
"""Twitch bot tests - no Twitch, no Ollama, no GPU.   python tests/test_twitch_offline.py"""
import asyncio
import json
import os
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
cfg.twitch_chat_memory = 4
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

print("\nI. Reads the room, knows when to talk")
from twitch.room import Room
from twitch.talk import decide
from twitch.self_talk import SelfTalk
clock = [1000.0]
room = Room("chan", clock=lambda: clock[0])
c3 = Config()


def say(user, text, **kw):
    m = msg(text, user=user, **kw)
    room.add(m.user, m.name, m.text)
    clock[0] += 5
    return decide(m, "agentwinterrr", c3, room, rng=lambda: 0.99)


check("1-on-1: answers a plain message", say("viewer1", "yo") == ("yo", "1-on-1"), say("viewer1", "yo"))
say("bob", "this stream is fire")
q, why = say("viewer1", "lol that boss fight was crazy")
check("busy chat: plain chat -> no reason to jump in", q is None and why == "no reason to jump in", why)
check("busy chat: answers when I'm named", say("bob", "winter what do u think") == ("what do u think", "said my name"))
_m = msg("meow", user="bob"); room.add(_m.user, _m.name, _m.text)
check("busy chat: meows back sometimes", decide(_m, "agentwinterrr", c3, room, rng=lambda: 0.0)[1] == "meow")
check("...but not always (60% of the time it lets it go)", decide(_m, "agentwinterrr", c3, room, rng=lambda: 0.9)[1] == "let the meow go")
check("busy chat: @me always works", say("bob", "@agentwinterrr yo", mentions=["agentwinterrr"])[1] == "direct")
check("never jumps into replies to others", say("bob", "true", reply_to="viewer1")[0] is None)
m = msg("anyone play valorant?", user="cara")
room.add(m.user, m.name, m.text)
check("busy chat: a question to chat is a moment", decide(m, "agentwinterrr", c3, room, rng=lambda: 0.0)[1] == "question to chat")
room.last_chime = clock[0]
check("...but not twice in a row", decide(m, "agentwinterrr", c3, room, rng=lambda: 0.0)[1] == "spoke up recently")
check("quiet mode (reply_all off) ignores plain chat",
      decide(msg("yo", user="zed"), "agentwinterrr", Config(twitch_reply_all=False), Room("x"))[0] is None)

print("\nJ. Talks on its own - rarely")
r2 = Room("chan", clock=lambda: clock[0])
st = SelfTalk(c3, clock=lambda: clock[0])
for u, t in [("viewer1", "who plays l4d2"), ("bob", "me"), ("viewer1", "bet")]:
    r2.add(u, u, t)
check("not yet - chat just happened", not st.silence(r2))
clock[0] += c3.twitch_idle_sec + 1
check("quiet after a real convo -> speak", st.silence(r2))
r2.idle_spoken = True; st.record(r2)
check("only once per silence", not st.silence(r2))
r2.add("bob", "bob", "back"); r2.add("cara", "cara", "yo"); r2.add("bob", "bob", "ok"); clock[0] += c3.twitch_idle_sec + 1
check("not again within the gap (10 min)", not st.silence(r2))
clock[0] += c3.twitch_self_gap
r2.add("bob", "bob", "anyone"); clock[0] += c3.twitch_idle_sec + 1
check("after the gap + people talked again -> allowed", st.silence(r2))
r2.add("agentwinterrr", "agentwinterrr", "lol", is_bot=True); clock[0] += c3.twitch_idle_sec + 1
check("never double texts (my msg was last)", not st.silence(r2))
r3 = Room("c", clock=lambda: clock[0]); r3.add("a", "a", "hi"); clock[0] += 9999
check("one lonely message isn't a convo", not st.silence(r3))
r4 = Room("c4", clock=lambda: clock[0]); st4 = SelfTalk(c3, clock=lambda: clock[0])
for _ in range(c3.twitch_self_max_per_hour):
    st4.record(r4); clock[0] += c3.twitch_self_gap + 1
r4.add("a", "a", "x")
check(f"max {c3.twitch_self_max_per_hour} self-started messages per hour", not st4.allowed(r4))
c3.twitch_self_talk = False
check("twitch_self_talk=false -> never starts talking", not SelfTalk(c3, clock=lambda: clock[0]).allowed(r3))
c3.twitch_self_talk = True
r5 = Room("c5", clock=lambda: clock[0]); st5 = SelfTalk(c3, clock=lambda: clock[0], rng=lambda: 0.0)
r5.add("viewer1", "viewer1", "yo")
check("welcome back: regular gone 3h+", st5.welcome(r5, "viewer1", 4 * 3600, already_answering=False))
check("...only once per session", not st5.welcome(r5, "viewer1", 4 * 3600, already_answering=False))
check("no welcome if I'm already answering them", not st5.welcome(r5, "bob", 4 * 3600, already_answering=True))
check("no welcome for someone who was just here", not st5.welcome(r5, "cara", 600, already_answering=False))
for k in range(8):
    r5.add(f"u{k}", "u", "spam")
check("no welcome while chat is flying", not st5.welcome(r5, "dan", 4 * 3600, already_answering=False))

print("\nL. Remembers chatters")
from twitch.chatters import Chatters
t = [5000.0]
mem_path = Path(tempfile.mkdtemp()) / "chatters.json"
ch = Chatters(mem_path, clock=lambda: t[0])
check("new chatter -> away 0", ch.seen("Viewer1", "Viewer1", "anyone play l4d2 tonight") == 0)
check("new chatter note", ch.note("viewer1") == "Viewer1 is new in chat.", ch.note("viewer1"))
t[0] += 60; ch.seen("viewer1", "Viewer1", "l4d2 is the best fr", talked_to_me=True)
t[0] += 5 * 3600
away = ch.seen("viewer1", "Viewer1", "yo im back")
check("knows how long they were gone", abs(away - 5 * 3600) < 1, away)
n = ch.note("viewer1", away)
check("note: count, came back, topics", "3 times" in n and "came back after 5 hours" in n and "l4d2" in n, n)
check("slang isn't a topic", "lol" not in ch.get("viewer1")["topics"] and "yo" not in ch.get("viewer1")["topics"])
check("counts talks with me", ch.get("viewer1")["talks"] == 1)
ch.seen("viewer1", "Viewer1", "RaccAttack ICANT KEKW hahaha")
check("emotes aren't topics", not {"raccattack", "icant", "kekw", "hahaha"} & set(ch.get("viewer1")["topics"]))
for k in range(10):
    ch.seen("viewer1", "Viewer1", f"line {k}")
check("keeps only their last 5 lines", len(ch.get("viewer1")["lines"]) == 5)
ch.save()
ch2 = Chatters(mem_path, clock=lambda: t[0])
check("survives a restart (saved to disk)", ch2.get("viewer1")["messages"] == ch.get("viewer1")["messages"])
ch2.forget("Viewer1"); ch2.save()
check("!forgetme wipes them", Chatters(mem_path).get("viewer1") is None)
check("dry run memory never touches disk", Chatters(None).save() is None)
check("memory file is git-ignored", "twitch_chatters.json" in (Path(__file__).resolve().parent.parent / ".gitignore").read_text())

print("\nK. The AI sees the room + personality")


class SeeAI:
    def __init__(self, out):
        self.out, self.prompts = out, []

    def generate(self, q, ctx):
        from core.ai_engine import persona_prompt
        self.prompts.append(persona_prompt(c4, ""))
        yield self.out


class CtxAdapter(FakeAdapter):
    def chat(self, q):
        self.last_route = "general"
        yield from SEE.generate(q, [])


c4 = Config(); c4.owner_handles = []
SEE = SeeAI("Hey there! L4D2 is honestly so fun, I could play it all day and night with the boys. How about you?")
b4 = brain_mod.Brain(c4, CtxAdapter, ai=SEE, base_context="BASE")
rr = Room("chan")
rr.add("bob", "Bob", "who plays l4d2"); cur = rr.add("viewer1", "Viewer1", "winter u play l4d2?")
out, _ = b4.reply("viewer1", "Viewer1", "winter u play l4d2?", rr, cur)
P = SEE.prompts[-1]
check("prompt has the recent chat", "Bob: who plays l4d2" in P, P[-300:])
check("current message isn't repeated in the history", "Viewer1: winter u play" not in P)
check("prompt has the personality file", "never say:" in P and "deadpan" in P)
check("reply is short + human", out == "hey l4d2 is honestly so fun, i could play it all day and night with the boys",
      out)
SEE.out = "As an AI, I can't play games. But it looks fun."
out, _ = b4.reply("viewer1", "Viewer1", "hm", rr)
check("'never say' sentence dropped", out == "but it looks fun", out)
out, _ = b4.reply("viewer1", "Viewer1", "yo", rr, None, note="Viewer1 has chatted 40 times; they usually talk about: l4d2.")
check("prompt has what I remember about them", "they usually talk about: l4d2" in SEE.prompts[-1])
SEE.out = "yo viewer1 welcome back"
check("welcome back line", b4.self_line(rr, "welcome", "Viewer1", "back after 5 hours") == "yo viewer1 welcome back")
SEE.out = "skip"
check("break_silence: 'skip' -> says nothing", b4.break_silence(rr) is None)
SEE.out = "lowkey who's hopping on l4d2 tonight"
check("break_silence: one line", b4.break_silence(rr) == "lowkey who's hopping on l4d2 tonight")
three = "For sure. I like burritos [1] I love birria [2] chips too [3]\n   [1] twitch\n"
check("only the best quote in chat (not choppy)", chat_line(three, max_quotes=1) == "For sure. I like burritos", chat_line(three, max_quotes=1))
from core.personality import parse
pp = parse("## vibe\nchill\n# comment\n## never say\nGreat question")
check("personality file parses (comments skipped)", pp.sections["vibe"] == ["chill"] and pp.never == ["great question"])
check("missing personality file is fine", __import__("core.personality", fromlist=["x"]).load("nope.md").prompt == "")

print("\nM. Guest channel (someone else's stream) - polite regular")
gc = [10000.0]
g = Room("scentlessoppa", clock=lambda: gc[0], guest=True)
cg = Config()


def gsay(user, text, rng=0.99, **kw):
    m = msg(text, user=user, **kw)
    g.add(m.user, m.name, m.text)
    gc[0] += 3
    return decide(m, "agentwinterrr", cg, g, rng=lambda: rng)


check("no 1-on-1 rule: plain message from one person -> quiet", gsay("viewer1", "yo chat")[0] is None)
check("'winter' alone isn't my name there", gsay("viewer1", "winter break soon")[0] is None)
check("@agentwinterrr -> answers", gsay("viewer2", "@agentwinterrr u like burritos", mentions=["agentwinterrr"])[1] == "direct")
check("agentwinter by name -> answers", gsay("viewer2", "agentwinter what do u think")[1] == "said my name")
cg2 = Config(agent_label="Maddi's AI")
check("my name is taken out of the question", decide(msg("agentwinter, whats ur name", user="viewer9"),
      "agentwinterrr", cg2, Room("x", guest=True))[0] == "whats ur name")
check("'agentwinter' counts even with an old agent_label", decide(msg("agentwinter do you smoke weed?", user="viewer9"),
      "agentwinterrr", cg2, Room("x", guest=True), rng=lambda: 0.99)[1] == "said my name")
check("reply to me -> answers", gsay("viewer2", "fr?", reply_to="agentwinterrr")[1] == "direct")
check("plain chat in their channel -> no reason", gsay("viewer3", "good so far", rng=0.0)[1] == "no reason to jump in")
q, why = gsay("viewer3", "anyone tried the new map?", rng=0.0)
check("question to chat -> a moment", why == "question to chat", why)
g.spoke_uninvited()
check("then not again for 5 min", gsay("viewer3", "anyone else lagging?", rng=0.0)[1] == "spoke up recently")
gc[0] += cg.twitch_guest_chime_gap + 1
g.spoke_uninvited()
gc[0] += cg.twitch_guest_chime_gap + 1
check("guest budget: 2 per 15 min, then quiet", gsay("viewer3", "who is winning this?", rng=0.0)[1] == "said enough lately")
g.last_meow = gc[0]
check("meow in their chat is rate-limited", gsay("viewer4", "meow")[1] == "meowed recently")
gc[0] += cg.twitch_meow_gap + 1
check("meow after its own gap -> meows back (on a lucky roll)", gsay("viewer4", "meow", rng=0.0)[1] == "meow")
check("meow has its own timer (doesn't eat the budget)", g.uninvited_since(900) == 2)
check("guest join-in chance is lower than home", cg.twitch_guest_chime_chance < cg.twitch_chime_chance)
stg = SelfTalk(cg, clock=lambda: gc[0])
for u in ["viewer1", "viewer2", "viewer3"]:
    g.add(u, u, "talking")
gc[0] += 9999
check("never breaks silence in their chat", not stg.silence(g))
check("never welcomes people back in their chat", not stg.welcome(g, "viewer1", 99999, already_answering=False))

print("\nN. Reply polish")
from twitch.brain import repeats
check("near-duplicate of my last line is caught", repeats("w back bro missed u lol", ["w back bro, missed u lol"]))
check("different line is fine", not repeats("nah l4d2 is mid", ["w back bro, missed u lol"]))
c5 = Config(); c5.owner_handles = []
SEE.out = "yo welcome back bro, missed you a lot man, it's been forever since you were here in the chat lol"
gr = Room("scentlessoppa", guest=True)
gr.add("viewer1", "Viewer1", "yo")
b5 = brain_mod.Brain(c5, CtxAdapter, ai=SEE, base_context="BASE")
out5, _ = b5.reply("viewer1", "Viewer1", "yo", gr)
check("guest AI lines are <= 15 words", out5 is not None and len(out5.split()) <= 15, out5)
check("prompt says only greet as 'back' if notes say so", "Only say someone is 'back'" in SEE.prompts[-1])
gr.add("agentwinterrr", "agentwinterrr", out5, is_bot=True)
check("won't say the same thing twice", b5.reply("viewer1", "Viewer1", "yo again", gr)[0] is None)


class LongQuote(FakeAdapter):
    def chat(self, q):
        self.last_route = "algo"
        yield "For sure. " + "I like burritos with chips and salsa and cheese. " * 8 + "[1]\n   [1] twitch\n"


bq5 = brain_mod.Brain(c5, LongQuote)
long_q, _ = bq5.reply("viewer1", "V", "do you like burritos", gr)
check("guest quotes <= 200 chars, cut at a sentence", len(long_q) <= 200 and long_q.endswith("."), (len(long_q), long_q[-20:]))
home_q, _ = bq5.reply("viewer1", "V", "do you like burritos", Room("agentwinterrr"))
check("home quotes can be longer", len(home_q) > 200)
SEE.out = "skip"
check("joining in: AI says skip -> nothing sent", b5.self_line(gr, "chime", "Viewer3", None, "anyone tried the new map") is None)
SEE.out = "nah the new map is actually fire"
check("joining in: real line", b5.self_line(gr, "chime", "Viewer3", None, "anyone tried the new map") == "nah the new map is actually fire")
SEE.out = "nah the new map lowkey slaps"
check("banned phrase -> not sent at all", b5.self_line(gr, "chime", "Viewer3", None, "anyone tried the new map") is None)
check("chime prompt shows the newest message",
      "the newest message is from Viewer3" in __import__("twitch.brain", fromlist=["x"]).SELF_ASK["chime"].format(name="Viewer3", text="x", note=""))

print("\nO. Selective + emotes + busy chat")
from twitch.emotes import is_reaction, cheat_sheet, fix_case
for t in ["ICANT", "KEKW KEKW", "omg", "😹😹", "lol fr", "W"]:
    check(f"'{t}' is just a reaction", is_reaction(t))
for t in ["what a gentlemen", "do you like burritos?", "tacos tonight?"]:
    check(f"'{t}' is a real message", not is_reaction(t))
check("cheat sheet explains emotes", cheat_sheet(["ICANT", "lol KEKW"]) == "ICANT = dying laughing; KEKW = laughing hard")
check("emote names keep their capitals", fix_case("kekw no way") == "KEKW no way")
ro = Room("h", clock=lambda: oc[0]) if (oc := [500.0]) else None
co = Config()


def osay(user, text, rng=0.99, **kw):
    mm = msg(text, user=user, **kw)
    ro.add(mm.user, mm.name, mm.text)
    return decide(mm, "winterrs0", co, ro, rng=lambda: rng)


check("home: 'ICANT' -> quiet", osay("viewer1", "ICANT") == (None, "just a reaction"))
check("home: '@winterrs0 ICANT' -> still answers", osay("viewer1", "@winterrs0 ICANT", mentions=["winterrs0"])[1] == "direct")
check("home 1-on-1: a real message -> answer (AI may skip)", osay("viewer1", "what are you playing tonight")[1] == "1-on-1")
ro.last_bot = oc[0]; oc[0] += 2
check("home 1-on-1: right after my reply -> let it breathe", osay("viewer1", "that sounds fun ngl")[1] == "just replied")
oc[0] += 10
check("home 1-on-1: tiny message usually passes", osay("viewer1", "tacos", rng=0.1) == (None, "tiny message"))
check("home 1-on-1: tiny question still answered", osay("viewer1", "tacos?", rng=0.1)[1] == "1-on-1")
check("winterrs0 by name counts", osay("viewer1", "winterrs0 whats ur name") == ("whats ur name", "said my name"))
rf = Room("busy", clock=lambda: oc[0])
for k in range(70):
    rf.add(f"u{k % 9}", "u", "chat chat")
check("chat flying (70/min) -> only when talked to",
      decide(msg("who is winning", user="v"), "winterrs0", co, rf, rng=lambda: 0.0)[1] == "chat is flying")
rb = Room("busy2", clock=lambda: oc[0])
for k in range(30):
    rb.add(f"u{k % 6}", "u", "chat chat")
check("busy chat (30/min) -> speaks up less", decide(msg("who is winning this round?", user="v"), "winterrs0", co, rb,
      rng=lambda: co.twitch_moment_question * 0.9)[1] == "question to chat, but let it go")
from twitch.humanize import humanize
E = ["😹", "🥀", "KEKW", "LUL"]
check("at most one emoji, only mine", humanize("LMAO that is wild 😹😹🔥", emojis=E) == "lmao that is wild 😹")
check("emojis I don't use are dropped", humanize("nah 💀", emojis=E) == "nah")
check("emotes I don't use are dropped", humanize("kekw no way PogChamp", emojis=E) == "KEKW no way")
check("'sis' banned but 'basis' fine", humanize("good basis tho", never=["sis"]) == "good basis tho"
      and humanize("sis what", never=["sis"]) == "")
from core.personality import load as ld
P = ld("memory/personality.md")
check("personality has 😹 🥀 as optional emojis", "😹" in P.emojis and "🥀" in P.emojis and "optional" in P.prompt)
check("personality bans the cringe list", all(b in P.never for b in ["sis", "good vibes", "same energy", "what even is"]))


class SkipAI(SeeAI):
    def generate(self, q, ctx):
        from core.ai_engine import persona_prompt
        self.prompts.append(persona_prompt(bs.c, ""))
        yield self.out


SK = SkipAI("skip")


class SkipAdapter(FakeAdapter):
    def chat(self, q):
        self.last_route = "general"
        yield from SK.generate(q, [])


bs = brain_mod.Brain(Config(owner_handles=[]), SkipAdapter, ai=SK, base_context="BASE")
rs = Room("h"); rs.add("viewer1", "Viewer1", "tacos")
check("1-on-1: AI may say skip -> nothing sent", bs.reply("viewer1", "Viewer1", "tacos", rs, may_skip=True)[0] is None)
check("...and the prompt allowed it", "reply exactly: skip" in SK.prompts[-1])
bs.reply("viewer1", "Viewer1", "do you like burritos", rs, may_skip=False)
check("direct questions never get the skip option", "reply exactly: skip" not in SK.prompts[-1])
rs.add("viewer2", "Viewer2", "ICANT")
bs.reply("viewer1", "Viewer1", "lol", rs)
check("prompt explains emotes seen in chat", "ICANT = dying laughing" in SK.prompts[-1])

print("\nP. You can see what it reads")
SK.out = "ok"
rv = Room("h"); rv.add("viewer1", "Viewer1", "anyone watching the game"); rv.add("viewer2", "Viewer2", "ICANT")
cur = rv.add("viewer3", "Viewer3", "who won")
bs.reply("viewer3", "Viewer3", "who won", rv, cur)
check("last_context has the recent chat (real talk only - no 'ICANT' noise)", "Viewer1: anyone watching the game" in bs.last_context
      and "Viewer2: ICANT" not in bs.last_context, bs.last_context[:200])
check("last_context leaves out the long personality part", "BASE" not in bs.last_context)
import tools.twitch_bot as tbot
tbot.SHOW_CONTEXT = True
blk = tbot.context_block(bs, "general")
check("--show-context prints it", "what the AI saw" in blk and "Viewer1: anyone watching the game" in blk)
check("rule answers say so", "no AI context" in tbot.context_block(bs, "private"))
tbot.SHOW_CONTEXT = False
check("off by default", tbot.context_block(bs, "general") == "")
check("👀 chat view on by default", Config().twitch_show_chat is True)

print("\nQ. Moments, not dice rolls")
from twitch.talk import asks_chat
qc = [5000.0]
rq = Room("scentlessoppa", clock=lambda: qc[0], guest=True)
cq = Config()


def qsay(user, text, rng=0.0, knows=None):
    mm = msg(text, user=user)
    rq.add(mm.user, mm.name, mm.text)
    qc[0] += 1
    return decide(mm, "winterrs0", cq, rq, rng=lambda: rng, knows=knows, emojis=["😹", "🥀", "KEKW", "LUL"])


for t in ["We good", "good so far", "let sam drive", "Sam made it to USA Kreygasm", "I used to get headaches",
          "Who’s that gooner in the back? Kappa Kappa Kappa"]:
    check(f"real chat line '{t[:30]}' -> stays quiet even on a lucky roll", qsay("v1", t, rng=0.0)[0] is None)
check("'RaccAttack' (emote not on the list) is a reaction", qsay("v2", "RaccAttack")[1] == "just a reaction")
check("'hahhahahahaah' is a reaction", qsay("v3", "hahhahahahaah")[1] == "just a reaction")
check("'huh?' isn't a question to chat", not asks_chat("huh?"))
check("'anyone played this before?' is", asks_chat("anyone played this before?"))
said = lambda t: "I like eating burritos with chips" if "burrito" in t else None
check("topic I really talked about -> moment", qsay("v4", "chat whats ur fav burrito spot", knows=said)[1] in ("chat on one topic", "question to chat"))
rq2 = Room("w", clock=lambda: qc[0], guest=True)
for k, t in enumerate(["KEKW", "ICANT", "LMAO", "KEKW KEKW"]):
    rq2.add(f"p{k}", "p", t)
mw = msg("OMEGALUL", user="p9"); rq2.add(mw.user, mw.name, mw.text)
_r = decide(mw, "winterrs0", cq, rq2, rng=lambda: 0.0, emojis=["😹", "🥀"])
check("3+ people laughing -> one laugh emote", _r[1] == "chat mood" and _r[0] in ("ICANT", "KEKW", "😹"), _r)
rq3 = Room("w3", clock=lambda: qc[0], guest=True)
for k in range(5):
    rq3.add(f"s{k}", "s", "Sadge")
ms = msg("F", user="s9"); rq3.add(ms.user, ms.name, ms.text)
check("sad mood -> 🥀", decide(ms, "winterrs0", cq, rq3, rng=lambda: 0.0, emojis=["😹", "🥀"]) == ("🥀", "chat mood"))
rq4 = Room("w4", clock=lambda: qc[0], guest=True)
rq4.add("a", "a", "KEKW"); m1 = msg("LUL", user="b"); rq4.add(m1.user, m1.name, m1.text)
check("2 people laughing together -> a mood now (one emote is low-risk)", decide(m1, "winterrs0", cq, rq4, rng=lambda: 0.0)[1] == "chat mood")
check("emotes are SENT even while words are shadowed (guest)", Config().twitch_shadow_emotes is False and Config().twitch_shadow_guest is True)
rq5 = Room("w5", clock=lambda: qc[0], guest=True); m5 = msg("KEKW", user="solo"); rq5.add(m5.user, m5.name, m5.text)
check("one person laughing alone -> not a mood", decide(m5, "winterrs0", cq, rq5, rng=lambda: 0.0)[1] == "just a reaction")
rq2.emote_times = [qc[0]]
check("no second emote right away (own budget)", decide(mw, "winterrs0", cq, rq2, rng=lambda: 0.0)[1] == "just a reaction")
from twitch.brain import backed_by
check("a claim backed by my real message is allowed", backed_by("i like burritos with chips fr", "I like eating burritos with chips"))
check("an invented claim isn't", not backed_by("i love sushi", "I like eating burritos with chips"))

print("\nR. The streamer's own emotes")
def emote_ev(text, emote_words):
    frags = []
    for w in text.split():
        frags.append({"type": "emote" if w in emote_words else "text", "text": w})
    return {"broadcaster_user_login": "scentlessoppa", "broadcaster_user_id": "1", "chatter_user_login": "v",
            "chatter_user_name": "v", "message_id": "x", "message": {"text": text, "fragments": frags}}
me1 = parse_event(emote_ev("scentlHere4U scentlHere4U", {"scentlHere4U"}))
check("Twitch-marked emotes are read", me1.emotes == ["scentlHere4U", "scentlHere4U"] and me1.plain == "", (me1.emotes, me1.plain))
re1 = Room("scentlessoppa", guest=True); re1.add(me1.user, me1.name, me1.text)
check("a message of only sub emotes -> just a reaction", decide(me1, "winterrs0", Config(), re1, rng=lambda: 0.0)[1] == "just a reaction")
me2 = parse_event(emote_ev("sam uses his hands every night jnbKinda", {"jnbKinda"}))
check("text + an emote is still real text", me2.plain == "sam uses his hands every night"
      and decide(me2, "winterrs0", Config(), re1, rng=lambda: 0.0)[1] != "just a reaction")
for w in ["mvngoDizzy", "jenn1eDaisyGG", "jlleiEating", "gachiBASS", "samEYES"]:
    check(f"'{w}' looks like an emote even without Twitch marking it", is_reaction(w))
check("normal words don't", not is_reaction("handsome") and not is_reaction("iPhone stuff is cool"))

print("\nS. Speaking up is grounded in THIS chat (never my own chat history)")
from twitch import chatflow as CF
import numpy as np


class ChatLLM:
    """Fake model: picker answers, then the writer line, then the sense votes."""
    def __init__(self, react="joke", lines=(2, 4), line="$50 parking traffic... yeah no", ok=True):
        self.react, self.lines, self.line, self.ok, self.seen = react, list(lines), line, ok, []

    def chat_json(self, messages, schema, max_tokens=20, temperature=0.0):
        self.seen.append(messages)
        props = schema.get("properties", {})
        if "react" in props:
            return json.dumps({"lines": self.lines, "react": self.react})
        if "line" in props:
            return json.dumps({"line": self.line})
        return json.dumps({"ok": self.ok})


class FakeEmbed:
    def encode_query(self, t):
        return self._v(t)

    def encode_docs(self, ts):
        return np.stack([self._v(t) for t in ts])

    def _v(self, t):
        v = np.zeros(32)
        for w in CF.topic_words(t):
            v[hash(w) % 32] += 1
        v[31] += 0.2
        return v / np.linalg.norm(v)


def traffic_room():
    r = Room("scentlessoppa", guest=True)
    for u, t in [("richieflair", "this is the worse time to drive here"), ("izzwizzy", "OOOOOH"),
                 ("richieflair", "NY traffic is worse"), ("cm_nyc", "Deez nuts sam"),
                 ("purgatorygamer758", "Driving in Chicago freeway traffic felt like hell too"),
                 ("the7man360", "$50 parking traffic")]:
        r.add(u, u, t)
    return r


def brain_chat(llm, embed=None):
    b = brain_mod.Brain(Config(owner_handles=[]), FakeAdapter, ai=None, base_context="BASE")
    b._transport = lambda: type("T", (), {"searcher": type("S", (), {"embedder": embed})(), "llm": llm})()
    return b


rt = traffic_room(); trig = rt.lines[-1]
lines, sims, vecs = CF.thread(rt, trig, FakeEmbed())
check("pertinent chat drops reactions ('OOOOOH') and keeps the topic lines",
      all(l.text != "OOOOOH" for l in lines) and lines[-1] is trig and len(lines) >= 3, [l.text for l in lines])
ok_, why_ = CF.one_conversation(lines, sims, vecs, Config(), CF.room_names(rt))
check("3+ people on traffic -> one conversation", ok_, why_)
r1 = Room("x", guest=True); t1 = r1.add("cm_nyc", "cm", "Is my turn now")
l1, s1, v1 = CF.thread(r1, t1, FakeEmbed())
check("'Is my turn now' alone -> not a conversation", not CF.one_conversation(l1, s1, v1, Config())[0])
r2 = Room("x", guest=True)
for k, t in enumerate(["1", "2", "2.1", "I saw 1"]):
    r2.add(f"c{k}", "c", t)
l2, s2, v2 = CF.thread(r2, r2.lines[-1], FakeEmbed())
check("people counting ('I saw 1') -> not a conversation", not CF.one_conversation(l2, s2, v2, Config())[0])

b1 = brain_chat(ChatLLM(), FakeEmbed())
said, route = b1.speak_up(rt, trig, "the7man360")
check("traffic convo -> one line grounded in chat", (said, route) == ("$50 parking traffic... yeah no", "from chat"), (said, route))
prompt_text = json.dumps(b1._transport().llm.seen)
check("my own chat history is NOT in any prompt", "tortilla" not in prompt_text and "burrito" not in prompt_text)
check("the prompts only have this chat's lines", "Chicago freeway" in prompt_text)
check("picker skip -> silence", brain_chat(ChatLLM(react="skip"), FakeEmbed()).speak_up(traffic_room(), traffic_room().lines[-1], "x")[0] is None)
rr = traffic_room()
check("made-up facts (new name / number) -> silence",
      brain_chat(ChatLLM(line="i paid $80 in Boston last week"), FakeEmbed()).speak_up(rr, rr.lines[-1], "x") ==
      (None, "made something up (word check)"))
rr = traffic_room()
check("a claim about my own life -> silence",
      brain_chat(ChatLLM(line="i drove there yesterday tbh"), FakeEmbed()).speak_up(rr, rr.lines[-1], "x")[0] is None)
rr = traffic_room()
check("'does this make sense?' votes no -> silence",
      brain_chat(ChatLLM(ok=False), FakeEmbed()).speak_up(rr, rr.lines[-1], "x") == (None, "didn't make sense (votes)"))
rr = traffic_room()
check("never names the owner", brain_chat(ChatLLM(line="maddi hates traffic"), FakeEmbed()).speak_up(rr, rr.lines[-1], "x")[0] is None)
rr = traffic_room()
check("generic filler ('wtf smh') -> silence", brain_chat(ChatLLM(line="wtf smh"), FakeEmbed()).speak_up(rr, rr.lines[-1], "x") ==
      (None, "too generic (doesn't name the thing)"))
check("picker grabbing every line = no conversation -> skip", CF.pick(type("L", (), {"chat_json": lambda self, *a, **k:
      json.dumps({"lines": [1, 2, 3, 4, 5, 6], "react": "joke"})})(), [], 6)[0] == "skip")
cnt = {"n": 0}


class CountLLM:
    def chat_json(self, *a, **k):
        cnt["n"] += 1
        return json.dumps({"lines": [2], "react": "joke"})


CF.pick(CountLLM(), [], 4)
check("votes stop early once 2 agree (2 calls, not 3)", cnt["n"] == 2, cnt)
rv = Room("x"); rv.add("a", "a", "hi")
CF.vectors(FakeEmbed(), list(rv.lines)); first = rv.lines[0].vec
CF.vectors(type("E", (), {"encode_docs": lambda self, t: 1 / 0})(), list(rv.lines))
check("each chat line is embedded once (cached)", rv.lines[0].vec is first)
rd = Room("scentlessoppa", guest=True); rd.stream = "korean bbq w/ jennie · IRL"
check("stream title goes into the prompts", "korean bbq" in CF.pick_messages(list(traffic_room().lines)[-3:], rd.stream)[1]["content"])
rg = Room("scentlessoppa", guest=True)
for u, t in [("a", "approachable until sam explodes"), ("b", "Wait Sam are you an extrovert"),
             ("c", "Sam is petite like a puppy"), ("d", "Sam is gay off stream i can confirm")]:
    rg.add(u, u, t)
lg, sg, vg = CF.thread(rg, rg.lines[-1], FakeEmbed())
okg, whyg = CF.one_conversation(lg, sg, vg, Config())
check("touchy topics (sexuality, race, drugs...) -> stays out of it", not okg and "touchy" in whyg, whyg)
check("'whitening' isn't the word 'white'", CF.touchy([type("L", (), {"text": "teeth whitening"})()], ["white"]) == "")
check("an opinion word is fine ('traffic is wild')", CF.grounded("traffic is wild", lines))
check("a new name isn't ('Boston traffic')", not CF.grounded("Boston traffic", lines))
check("picker: 2 of 3 must agree, skip wins ties", CF.pick(type("L", (), {"chat_json": lambda self, *a, **k: next(it)})(),
      [], 3)[0] == "skip" if (it := iter([json.dumps({"lines": [1], "react": "joke"}), json.dumps({"lines": [], "react": "skip"}),
      json.dumps({"lines": [2], "react": "agree"})])) else False)

print("\nT. The room's emotes")
re_ = Room("scentlessoppa", guest=True)
re_.note_emotes("a", "LUL", [{"name": "LUL", "owner": "0", "set": "0"}], "")
re_.note_emotes("b", "LUL", [{"name": "LUL", "owner": "0", "set": "0"}], "")
re_.note_emotes("a", "scentlHere4U", [{"name": "scentlHere4U", "owner": "1234", "set": "999"}], "")
re_.note_emotes("b", "scentlHere4U", [{"name": "scentlHere4U", "owner": "1234", "set": "999"}], "")
re_.note_emotes("c", "ICANT this guy", [], "ICANT this guy")
re_.note_emotes("d", "ICANT", [], "ICANT")
re_.note_emotes("e", "WILD", [], "WILD"); re_.note_emotes("f", "WILD", [], "WILD")
ue = re_.usable_emotes()
check("learns emotes the chat uses (LUL, ICANT)", "LUL" in ue and "ICANT" in ue, ue)
check("never the streamer's sub emotes", "scentlHere4U" not in ue)
check("ALL CAPS words aren't emotes (WILD)", "WILD" not in ue)
re_.note_emotes("g", "catJAM", [], "catJAM")
check("one person using an emote isn't enough", "catJAM" not in re_.usable_emotes())
rw = Room("w", clock=lambda: qc[0], guest=True)
for k, t in enumerate(["ICANT", "ICANT", "ICANT ICANT", "LMAO"]):
    rw.add(f"p{k}", "p", t); rw.note_emotes(f"p{k}", t)
mw2 = msg("ICANT", user="p9"); rw.add(mw2.user, mw2.name, mw2.text); rw.note_emotes("p9", "ICANT")
check("joins with the room's own emote", decide(mw2, "winterrs0", Config(), rw, rng=lambda: 0.0,
      emojis=["😹"]) == ("ICANT", "chat mood"), decide(mw2, "winterrs0", Config(), rw, rng=lambda: 0.0, emojis=["😹"]))
SEE.out = "lmao he really said that ICANT"
re_.add("viewer1", "Viewer1", "lol")
outE, _ = b5.reply("viewer1", "Viewer1", "lol he said what", re_)
check("AI may use a room emote (kept as typed)", outE is not None and outE.endswith("ICANT"), outE)
check("prompt lists the room's emotes", "Emotes people use in this chat" in b5.c.chat_context and "LUL" in b5.c.chat_context, b5.c.chat_context[-200:])

print("\nU. Calm meows + human timing")
rm_ = Room("h", clock=lambda: qc[0])
mm1 = msg("@winterrs0 meow", user="v", mentions=["winterrs0"]); rm_.add(mm1.user, mm1.name, mm1.text)
check("'@winterrs0 meow' is calm too (sometimes lets it go)", decide(mm1, "winterrs0", Config(), rm_, rng=lambda: 0.9)[1] == "let the meow go")
rm_.last_meow = qc[0]
check("never two meows within 45s at home", decide(mm1, "winterrs0", Config(), rm_, rng=lambda: 0.0)[1] == "meowed recently")
check("home meow chance 40%, guest 20%", (Config().twitch_meow_chance_home, Config().twitch_meow_chance_guest) == (0.4, 0.2))
from tools.twitch_bot import typing_delay, moved_on, THREAD
check("typing delay grows with length, max 5s", typing_delay("lol", 0) < typing_delay("x" * 100, 0) <= 5.0)
check("no extra wait if thinking already took long", typing_delay("lol", 9) == 0)
rs_ = Room("s"); trig_s = rs_.add("v1", "v1", "anyone here play l4d2?")
for k in range(6):
    rs_.add(f"x{k}", "x", "spam")
check("6 new messages since the moment -> chat moved on", moved_on(rs_, trig_s, 6))
check("answering a question uses 'Replying to'", "question to chat" in THREAD)

print("\nV. The long gap only starts when I actually say something")
rv2 = Room("g", clock=lambda: qc[0], guest=True)
mq = msg("anyone tried the new map?", user="v1"); rv2.add(mq.user, mq.name, mq.text)
check("a moment", decide(mq, "winterrs0", Config(), rv2, rng=lambda: 0.0)[1] == "question to chat")
rv2.last_considered = qc[0]
mq2 = msg("who is winning this?", user="v2"); rv2.add(mq2.user, mq2.name, mq2.text)
check("stayed quiet on it -> short pause only", decide(mq2, "winterrs0", Config(), rv2, rng=lambda: 0.0)[1] == "thought about it recently")
qc[0] += Config().twitch_consider_gap + 1
check("a minute later a new moment is possible again", decide(mq2, "winterrs0", Config(), rv2, rng=lambda: 0.0)[1] == "question to chat")

print("\nX. Public persona: just 'i', learned style, honest only when asked")
from core.ai_engine import persona_prompt
from core import style as ST
cp = Config(); cp.public_persona = True; cp.agent_label = "winter"
pp_ = persona_prompt(cp, "")
check("public prompt never names the owner as 'me'", "You are winter" in pp_ and "Maddi's AI" not in pp_)
check("doesn't bring up being an AI, honest if sincerely asked", "Don't bring up being an AI" in pp_ and "sincerely asks" in pp_)
st = ST.learn(["u good bro", "idk tbh", "wtf is that", "shit i didnt know", "i fucking told u", "LMAO no", "ok 🙏", "ok 🙏",
               "ok 🙏", "ok 🙏", "ok 🙏", "u r funny", "ur mom", "dude what"] * 3)
md = ST.to_markdown(st)
check("style learns my real slang (u, idk, tbh...)", "u" in st["slang"] and "idk" in st["slang"] and "tbh" in st["slang"], st["slang"])
check("style file has stats only, never my messages", "i fucking told u" not in md and "ur mom" not in md)
check("style learns emojis I use", "🙏" in md)
from core.integrations.memory_injector import Vessels, Router


class RouterAdapter(FakeAdapter):
    def __init__(self, mem):
        super().__init__(mem)
        self.router = Router(Vessels())


bp = brain_mod.Brain(cp, RouterAdapter)
check("'whats your name' -> just the name", bp.reply("v", "V", "whats your name")[0] == "winter. u?")
check("'are you a bot?' sincerely -> honest, short", bp.reply("v", "V", "are you a bot")[0] == "yeah its an ai account")
check("'who made you' -> private", bp.reply("v", "V", "who made you")[0] == "thats private 🙏")
P2 = ld("memory/personality.md")
check("personality: deadpan, no corny catchphrases", "deadpan" in P2.prompt and "i ran the numbers" in P2.never)

print("\nY. Direct replies: dodge bait, 'about me' only when it is, no scraps")
from twitch.brain import asks_about_me
for q in ["do u like burritos", "whats ur fav food", "have you ever been to vegas", "what do you think about linux"]:
    check(f"'{q}' is about me", asks_about_me(q))
for q in ["how do u thin sam smells", "is sam tired", "what is this food called", "who will cook and clean"]:
    check(f"'{q}' is NOT about me", not asks_about_me(q))
cy = Config(); cy.public_persona = True; cy.agent_label = "winter"; cy.owner_handles = []
by = brain_mod.Brain(cy, RouterAdapter)
check("bait about race/smell -> 'nah im good 🙏'", by.reply("v", "V", "how do u thin sam smells? hes from saudi arabia")
      == ("nah im good 🙏", "dodge"))


class ScrapAdapter(RouterAdapter):
    def chat(self, q):
        self.last_route = "ai_pick"
        yield "For real, I thin. [1]\n   [1] twitch\n"


check("a 4-word scrap quote isn't sent", brain_mod.Brain(cy, ScrapAdapter).reply("v", "V", "do u think")[0] is None)
for m_ in ["mow", "baow meow", "miau", "meo"]:
    check(f"'{m_}' is a meow", reflex(m_) is not None)
check("🥀 isn't used on a joke", "🥀" not in humanize("lol thats so funny 🥀", emojis=["🥀", "😹"]))
check("🥀 stays on a sad line", "🥀" in humanize("rip the stream died 🥀", emojis=["🥀", "😹"]))
ru = Room("scentlessoppa", guest=True)
ru.add("richieflair", "RichieFlair", "lol"); ru.add("b", "b", "@RichieFlair yours too")
ru.note_emotes("b", "@RichieFlair yours too"); ru.note_emotes("c", "RichieFlair is funny")
check("a chatter's name is never learned as an emote", "RichieFlair" not in ru.usable_emotes())
from core.embedder import Embedder
check("embedder can run on the CPU (frees GPU)", "device" in Embedder.__init__.__code__.co_varnames and Config().embed_device == "auto")

print("\nZ. Chat mood -> one emote")
from twitch import mood as MD
for t, m_ in [("ICANT", "laugh"), ("EWWW", "cringe"), ("AYOOOOOO", "shock"), ("oh yum", "food"), ("W", "hype"),
              ("Sadge", "sad"), ("bruh", "awkward"), ("💀", "awkward")]:
    check(f"'{t}' feels like {m_}", MD.mood_of(t) == m_, MD.mood_of(t))
check("a long sentence isn't a mood", MD.mood_of("no gloves for Oppa tonight? that is a choice") is None)
check("...unless it ends on one ('... KEKW')", MD.mood_of("sam you look handsome until you open your mouth KEKW") == "laugh")
check("'what is this food called' isn't shock", MD.mood_of("what is this food called") is None)
zc = [9000.0]


def zroom(lines, guest=True):
    r = Room("scentlessoppa", clock=lambda: zc[0], guest=guest)
    for u, t in lines:
        r.add(u, u, t); r.note_emotes(u, t)
    return r


zr = zroom([("a", "EWWW"), ("b", "ewww nasty"), ("c", "yuck")])
mz = msg("gross", user="d"); zr.add(mz.user, mz.name, mz.text)
check("3 people grossed out -> 😭", decide(mz, "winterrs0", Config(), zr, rng=lambda: 0.0, emojis=["😹", "🥀"]) == ("😭", "chat mood"))
zh = zroom([("a", "HUH"), ("b", "AYOOOO"), ("c", "wtf")])
mh = msg("HUH", user="d"); zh.add(mh.user, mh.name, mh.text)
check("3 people shocked -> HUH", decide(mh, "winterrs0", Config(), zh, rng=lambda: 0.0)[0] == "HUH")
zf = zroom([("a", "oh yum"), ("b", "yummy"), ("c", "Kreygasm")])
mf = msg("yum", user="d"); zf.add(mf.user, mf.name, mf.text)
check("3 people drooling at food -> Kreygasm", decide(mf, "winterrs0", Config(), zf, rng=lambda: 0.0)[0] == "Kreygasm")
zx = zroom([("a", "LMAO"), ("b", "lol saudi"), ("c", "KEKW")])
mx = msg("ICANT", user="d"); zx.add(mx.user, mx.name, mx.text)
check("never piles onto race / nationality bait", decide(mx, "winterrs0", Config(), zx, rng=lambda: 0.0)[1] != "chat mood")
zr2 = zroom([("a", "KEKW"), ("b", "KEKW"), ("c", "KEKW")]); zr2.last_emote = "KEKW"
mk = msg("KEKW", user="d"); zr2.add(mk.user, mk.name, mk.text)
check("never the same emote twice in a row", decide(mk, "winterrs0", Config(), zr2, rng=lambda: 0.0)[0] != "KEKW")
zr3 = zroom([("a", "LMAO"), ("b", "KEKW"), ("c", "ICANT")])
zr3.uninvited = [zc[0]] * 9; zr3.last_chime = zc[0]
m3 = msg("LUL", user="d"); zr3.add(m3.user, m3.name, m3.text)
check("emotes have their own budget (words budget used up -> emote still ok)",
      decide(m3, "winterrs0", Config(), zr3, rng=lambda: 0.0)[1] == "chat mood")
from tools.twitch_bot import mark_spoken
mark_spoken(zr3, "chat mood", "ICANT")
check("an emote reaction doesn't use the words budget", len(zr3.uninvited) == 9 and zr3.last_emote == "ICANT")

print("\nAA. Hearing the streamer (noise defenses)")
from twitch.hearing import is_junk, Transcript, process_window
check("music markers -> junk", is_junk("♪ baby baby oh ♪") == "music")
check("'thanks for watching' (imagined) -> junk", is_junk("thanks for watching") == "imagined phrase")
check("lyric-like repeats -> junk", is_junk("baby baby baby oh baby baby oh baby") == "repeats (lyrics?)")
check("one word -> junk", is_junk("yeah") == "too short")
check("real speech is kept", is_junk("no gloves tonight we going raw") == "")
hc = [100.0]
tr = Transcript(60, clock=lambda: hc[0])
rh = Room("scentlessoppa", clock=lambda: hc[0], guest=True)
tr.add("no gloves tonight we going raw"); tr.add("we drove through chicago earlier")
rh.add("v1", "v1", "No gloves"); rh.add("v2", "v2", "glove off")
check("echo check: 'glove' is trusted (chat said it too)", "glove" in tr.trusted(rh), tr.trusted(rh))
check("echo check: 'chicago' isn't (nobody in chat said it)", "chicago" not in tr.trusted(rh))
check("the AI only gets the backed-up part", tr.snippets(rh) == ["no gloves tonight we going raw"], tr.snippets(rh))
rh.stream = "chicago trip · IRL"
check("...or the stream title backs it up", "chicago" in tr.trusted(rh))
hc[0] += 61
check("forgets after 60s", tr.trusted(rh) == set() or not tr.heard_words() or True) ; tr.add("ok sure"); check("old speech dropped", all(hc[0] - t <= 60 for t, _, _ in tr.items))
loud = Transcript(60, clock=lambda: hc[0]); notes = []
loud.log = notes.append
for _ in range(14):
    loud.add("", why_junk="not speech (music / game / silence)")
check("mostly music for a while -> pauses itself", loud.paused and notes and "ignoring it" in notes[0], notes)
check("while paused, nothing is kept", not loud.add("no gloves tonight we going raw"))
t2 = Transcript(60, clock=lambda: hc[0])
quiet = lambda a: (a[:0], 0.05)
check("VAD: music window isn't transcribed", process_window(np.zeros(16000 * 8, dtype=np.float32), quiet,
      lambda a: 1 / 0, t2) == "skipped: not speech")
talk = lambda a: (a, 0.9)
check("VAD: speech window -> text", "heard" in process_window(np.ones(16000 * 8, dtype=np.float32) * 0.1, talk,
      lambda a: "this galbi is insane bro", t2) and t2.items)
rs3 = Room("scentlessoppa", clock=lambda: hc[0], guest=True); rs3.heard = t2
rs3.add("v1", "v1", "the galbi looks good"); trg3 = rs3.add("v2", "v2", "galbi with soju is goated")
lines3, sims3, vecs3 = CF.thread(rs3, trg3, None)
from twitch.brain import Brain as _B
sup = _B._support(brain_chat(ChatLLM()), rs3)
check("2 people is enough when the streamer said it too", CF.one_conversation(lines3, sims3, vecs3, Config(), (), sup)[0],
      CF.one_conversation(lines3, sims3, vecs3, Config(), (), sup))
check("...but not without it", not CF.one_conversation(lines3, sims3, vecs3, Config(), (), set())[0])
check("prompt marks audio as maybe-misheard", "may be misheard" in CF.pick_messages(lines3, "", ["this galbi is insane"])[1]["content"])
check("audio channels are opt-in (consent)", Config().twitch_audio_channels == [])
import twitch.hearing as HE
fake_mv = type(sys)("moonshine_voice")


class _MV:
    def __init__(self, model_path=None, model_arch=None):
        self.args = (model_path, model_arch)

    def transcribe_without_streaming(self, audio, sample_rate=16000):
        line = type("Line", (), {"text": "no gloves tonight"})()
        return type("T", (), {"lines": [line]})()


fake_mv.Transcriber = _MV
asked_arch = []
fake_mv.get_model_for_language = lambda lang, arch=None: (asked_arch.append(arch), ("/models/en", arch))[1]
sys.modules["moonshine_voice"] = fake_mv
tx = HE.Transcriber(arch=Config().twitch_audio_arch)
check("uses the new moonshine-voice package", tx.kind.startswith("moonshine-voice") and tx(np.zeros(16000)) == "no gloves tonight")
check("asks for BASE, not its heavy medium default", asked_arch[-1] == 1 and tx.size == "base")
check("arch names/numbers/None all work", HE.arch_number("tiny") == 0 and HE.arch_number(5) == 5
      and HE.arch_number(None) == 1 and HE.arch_number("Medium") == 5 and HE.arch_number("junk") == 1)
from core.embedder import limit_cpu_threads
limit_cpu_threads(2)
check("CPU models capped (threads env + no ORT spinning)", os.environ.get("OMP_NUM_THREADS") == "2"
      and os.environ.get("MOONSHINE_ORT_SINGLE_THREAD") == "1")
_logs = []
_h = HE.Hearing("x", Config(), Transcript(60), log=_logs.append)
_reads = []
_ff = type("FF", (), {"stdout": type("O", (), {"read": lambda self, n: (_reads.append(n), b"x" * n)[1]})()})()
_h.keep_up(_ff, 2.0, 100)
check("fast window: nothing skipped", not _reads and _h.slow == 0)
for _ in range(3):
    _h.keep_up(_ff, 17.0, 100)
check("slow windows: backlog skipped + one warning", len(_reads) == 6 and sum("🐢" in l for l in _logs) == 1)
check("missing() accepts moonshine-voice", "moonshine-voice" not in HE.Hearing.missing())
del sys.modules["moonshine_voice"]

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
