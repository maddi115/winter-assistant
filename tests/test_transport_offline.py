#!/usr/bin/env python
"""Offline tests for the router, retrieval and transport model.

No Ollama and no embedding download needed: uses a fake embedder and a fake AI.
Run from the winter-assistant folder:   python tests/test_transport_offline.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import lancedb
import numpy as np
import pandas as pd

from core.config import Config
from core.integrations.memory_injector import Vessels, Router, Formatter
from retrieval.gradient import GradientProximitySearch, tokenize, stem
from retrieval.evidence_search import EvidenceSearch
from storage.evidence_store import EvidenceStore, evidence_schema, TABLE, has_table
from transport import TransportModel
from transport.checker import parse_reply, check_opener
from transport.packer import cosmetic
from transport.verdict import polarity
from adapters.conversation_adapter import ConversationAdapter

PASSED, FAILED = [], []


def check(name, cond, info=""):
    (PASSED if cond else FAILED).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + ("" if cond else f"   -> {info}"))


class FakeEmbedder:
    """Bag-of-words hashing vectors: similar words -> similar vectors."""
    dim = 256

    def _vec(self, text):
        v = np.zeros(self.dim, dtype=np.float32)
        for w in tokenize(text):
            h = int(hashlib.md5(stem(w).encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode_docs(self, texts):
        return np.stack([self._vec(t) for t in texts])

    def encode_query(self, text):
        return self._vec(text)


class FakeLLM:
    """Returns scripted ballots, one per call."""
    def __init__(self, ballots):
        self.ballots = list(ballots)
        self.calls = 0

    def chat_json(self, messages, schema, max_tokens=80, temperature=0.0):
        b = self.ballots[self.calls % len(self.ballots)]
        self.calls += 1
        return b


EVIDENCE = [   # (text, author, time) - times close together in one channel make a thread
    ("i like eating burritos xxtra hot cheetos and kombucha thats my combo guilty pleasure", "agentmaddi", "2025-06-10 12:00:00"),
    ("i like eating my burrito de birria with cheese its awesome", "agentmaddi", "2025-07-01 12:00:00"),
    ("lordmironia no bro i eat burritos", "agentmaddi", "2025-06-20 12:00:00"),
    ("i wanna eat hot cheetos and cheap pizza", "madddyyyyi", "2025-06-12 12:00:00"),
    ("i wanna buy pizza", "agentmaddi", "2025-06-15 12:00:00"),
    ("sometimes i play video games while listening to the stream", "agentmaddi", "2025-07-03 12:00:00"),
    ("when i gwow up i wanna be a streamer and play video games all day", "agentmaddi", "2025-07-09 12:00:00"),
    ("i dont like sushi at all", "agentmaddi", "2025-06-01 12:00:00"),
    ("ok i tried sushi again and i love it now", "agentmaddi", "2025-08-01 12:00:00"),
    ("i fell really hard from my stupid bicycle", "madddyyyyi", "2025-06-05 12:00:00"),
    ("i love pizza so much", "somebody_else", "2025-06-06 12:00:00"),   # NOT the owner
    ("there was a story about some restaurant owner harrassing a hotdog vendor", "agentmaddi", "2025-07-20 12:00:00"),
    ("of course with rice", "agentmaddi", "2025-07-05 14:00:10"),
    ("when my family folks make carne asada and pollo asada we like giving food the homeless people passing by our house", "agentmaddi", "2025-07-05 14:00:40"),
    ("i usually give food to homeless people only", "agentmaddi", "2025-07-05 14:01:20"),
    ("i might strreamsnipe and give u one when i get my third job", "agentmaddi", "2025-07-05 14:02:00"),
    ("my dad wouldve left the dog under a abandoned bridge", "agentmaddi", "2025-07-15 12:00:00"),
    ("chefie i fell off my bike", "agentmaddi", "2025-06-05 18:00:00"),
    ("its why i dont eat sheep burrito anymore", "agentmaddi", "2025-08-28 12:00:00"),
    ("its why i dont eat sheep burrito anymore", "agentmaddi", "2025-08-28 12:05:00"),   # sent twice
    ("favorite top movies drive the hateful eight pulp fiction dance scene", "agentmaddi", "2025-07-25 12:00:00"),
] + [(f"random chat line number {w} about the stream and stuff", "agentmaddi", f"2025-06-30 0{i % 10}:00:00")
     for i, w in enumerate(["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
               "eleven", "twelve", "lol", "bro", "chat", "hello", "goodnight", "gg", "wow", "nice"])]


def build(tmp, ballots=None, **overrides):
    config = Config()
    config.storage_path = tmp
    config.stability_min = 0.50
    config.confidence_min = 0.20    # fake embedder has a different scale than Qwen3
    for k, v in overrides.items():
        setattr(config, k, v)
    emb = FakeEmbedder()
    db = lancedb.connect(tmp)
    if not has_table(db, TABLE):
        owner = {h.lower() for h in config.owner_handles}
        df = pd.DataFrame({
            "id": range(len(EVIDENCE)),
            "text": [t for t, _, _ in EVIDENCE],
            "author": [a for _, a, _ in EVIDENCE],
            "is_owner": [a.lower() in owner for _, a, _ in EVIDENCE],
            "source": "twitch",
            "date": [ts[:10] for _, _, ts in EVIDENCE],
            "ts": [ts for _, _, ts in EVIDENCE],
            "channel": "artsycomicskid",
            "vector": [v.tolist() for v in emb.encode_docs([t for t, _, _ in EVIDENCE])],
        })
        db.create_table(TABLE, data=df, schema=evidence_schema(emb.dim))
    store = EvidenceStore(config, db=db)
    searcher = EvidenceSearch(store, emb, k=config.evidence_k)
    llm = FakeLLM(ballots) if ballots else None
    return config, store, TransportModel(config, searcher, llm=llm, style_samples=store.style_samples(5))


def main():
    tmp = tempfile.mkdtemp()

    print("\nA. Router (exact questions only)")
    r = Router(Vessels())
    f = Formatter("Maddi")
    check("'how do i store rice?' is NOT hijacked", r.route("how do i store rice?") == (None, None))
    check("'what model of car should i buy?' is NOT hijacked", r.route("what model of car should i buy?") == (None, None))
    check("'what city has the best tacos?' is NOT hijacked", r.route("what city has the best tacos?") == (None, None))
    k, d = r.route("What's your name?")
    check("'What's your name?' -> I'm agentWinter", k and f.format_response(k, d).startswith("I'm agentWinter"),
          f.format_response(k, d) if k else None)
    for q, want in [("whats my name", "Your name is Maddi"), ("who am i?", "Your name is Maddi"),
                    ("what gpu do i have?", "You have an NVIDIA"), ("where am i", "You're in Los Angeles"),
                    ("where are you from?", "I'm in Los Angeles")]:
        k, d = r.route(q)
        out = f.format_response(k, d) if k else None
        check(f"vessel: '{q}' -> '{want}...'", bool(out) and out.startswith(want), out)
    from core import colors
    colors.ENABLED = True
    k, d = r.route("whats my name")
    check("vessel value is highlighted neon pink", colors.PINK + "Maddi" in f.format_display(k, d))
    colors.ENABLED = False
    for q in ["hi whos ur owner?", "who made you", "whose ur owner", "who's your creator?"]:
        k, d = r.route(q)
        check(f"'{q}' -> 'Maddi made me'", k == "AI_OWNER" and "Maddi made me" in f.format_response(k, d), k)
    k, d = r.route("are you an ai?")
    check("'are you an ai?' -> honest AI label", k and "agentWinter, Maddi's AI" in f.format_response(k, d))

    print("\nD. Retrieval")
    g = GradientProximitySearch(["i eat burritos", "pizza and burritos and birria", "nothing here"])
    hits = dict(g.search("do you like burritos"))
    check("gradient: anchor-only doc no longer scores 0", hits.get(0, 0) > 0, hits)
    check("gradient: plural match burrito/burritos", dict(g.search("burrito")).get(0, 0) > 0)

    print("\nE. Verdict rules")
    check("'i dont like it' -> NO", polarity("i dont like it") == -1)
    check("'i dont hate it' -> unclear, not a flip", polarity("i dont hate it") == 0)
    check("'i know right' -> 'no' inside 'know' ignored", polarity("i know right") == 0)
    check("'not a fan' -> NO", polarity("honestly not a fan") == -1)
    check("'its like hot' -> filler 'like' ignored", polarity("its like hot outside") == 0)
    check("'i really love it' -> YES", polarity("i really love it") == 1)

    print("\nE. Checker / parser / cosmetic")
    check("messy reply 'I pick 1 and 3' -> [1, 3]", parse_reply("I pick 1 and 3")[0] == [1, 3])
    check("JSON reply parsed", parse_reply(json.dumps({"pick": [2], "opener": "oh yeah"})) == ([2], "oh yeah"))
    ev = ["i like eating my burrito de birria with cheese"]
    check("opener with invented number rejected", check_opener("I had it in 2019", ev, "q", "Maddi", 10) is None)
    check("opener with invented name rejected", check_opener("I go to Taco Bell", ev, "q", "Maddi", 10) is None)
    check("opener saying 'you said' rejected", check_opener("you said this", ev, "q", "Maddi", 10) is None)
    check("good opener kept", check_opener("oh for sure", ev, "q", "Maddi", 10) == "oh for sure.")
    raw = "i like eating burritos xxtra hot cheetos"
    out = cosmetic(raw)
    check("cosmetic: same words, only caps/punctuation",
          out.lower().rstrip(".").replace("I", "i") == raw.lower() and out.endswith("."), out)

    print("\nE. Transport model (algorithm only)")
    config, store, tm = build(tmp, transport_mode="algo")
    check("only the owner's messages are loaded", all(r["is_owner"] for r in store.rows))
    from core import colors
    colors.ENABLED = True
    res = tm.answer("do you like burritos?")
    colors.ENABLED = False
    print("     →", res.text.replace("\n", "\n       "))
    check("burritos -> YES with real quote", res.route == "algo" and ("burrito" in res.text.lower()), res.text)
    check("chat quotes highlighted neon green on screen, saved plain",
          colors.GREEN in res.display and colors.GREEN not in res.text, res.display)
    res = tm.answer("do you like pizza?")
    print("     →", res.text.replace("\n", "\n       "))
    check("pizza -> UNCLEAR (never a default YES)",
          any(o in res.text for o in ["not sure", "Not sure", "Kinda", "Hard to say"]), res.text)
    check("someone else's 'i love pizza' is never used", "so much" not in res.text)
    res = tm.answer("do you like sushi?")
    print("     →", res.text.replace("\n", "\n       "))
    check("sushi -> newest wins (changed mind)", res.text.lower().find("love it now") < res.text.lower().find("dont like")
          and "Before that" in res.text, res.text)
    res = tm.answer("do you have an owner?")
    print("     →", res.text)
    check("'restaurant owner' story (not about me) is never my answer", "restaurant" not in res.text, res.text)
    res = tm.answer("do you like quantum physics?")
    print("     →", res.text)
    check("no evidence -> idk in first person", res.route.startswith("idk"), res.route)

    print("\nE. Transport model (AI picks numbers, 3 votes)")
    q = "what games do you play?"
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [1, 2], "style": 2})] * 3,
                     winner_margin=0.9, agree_skip=False)      # force a close call so the AI is asked
    res = tm.answer(q)
    print("     →", res.text.replace("\n", "\n       "))
    check("votes agree -> AI picks used, real quotes shown", res.route == "ai_pick" and "video games" in res.text, (res.route, res.text))
    check("pick mode: opener chosen by number from the menu", res.text.startswith("Honestly,"), res.text)
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [1], "opener": "honestly nothing specific"})] * 3,
                     winner_margin=0.9, agree_skip=False, transport_mode="write")
    res = tm.answer(q)
    check("write mode: AI's own opener kept after checking", res.text.lower().startswith("honestly nothing specific"), res.text)
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [1], "opener": "a"}), json.dumps({"pick": [3], "opener": "b"}),
                                   json.dumps({"pick": [], "opener": "c"})], winner_margin=0.9, agree_skip=False)
    res = tm.answer(q)
    check("votes split -> idk", res.route == "idk_votes", res.route)
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [9, 1], "opener": "In 1999 I did"})] * 3,
                     winner_margin=0.9, agree_skip=False, transport_mode="write")
    res = tm.answer(q)
    check("bad number [9] dropped, bad opener replaced by template",
          res.route == "ai_pick" and "1999" not in res.text and "[2]" not in res.text, res.text)

    class DeadLLM:
        def chat_json(self, *a, **k):
            raise TimeoutError("timed out")
    config, store, tm = build(tmp, winner_margin=0.9, agree_skip=False)
    tm.llm = DeadLLM()
    res = tm.answer(q)
    check("AI timeout -> algorithm answers instead of hanging", res.route == "algo_fallback"
          and "video games" in res.text, (res.route, res.text))
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [1], "style": 1})] * 3)
    res = tm.answer("do you play video games?")
    check("yes/no + top results agree -> no AI needed", res.route == "algo", res.route)
    res = tm.answer("what games do you play?")
    check("open question -> agreement shortcut NOT used, AI decides", res.route == "ai_pick", res.route)
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [1], "style": 1})] * 3)
    res = tm.answer("what do you eat?")
    check("open question with a big lead -> still AI decides", res.route in ("ai_pick", "idk_gate", "idk_votes"), res.route)

    print("\nE. No repeats on follow-ups (adapter)")

    class MemStorage:
        def save_turn(self, *a, **k): pass
        def get_recent(self, n): return []
        def search(self, q, n): return []

    class NoAI:
        def generate(self, *_):
            yield "general"

    config, store, tm = build(tmp, transport_mode="algo")
    ad = ConversationAdapter(MemStorage(), type("R", (), {"retrieve": lambda s, *a, **k: []})(), NoAI(),
                             transport=tm, config=config)
    a1 = "".join(ad.chat("what do you think about burritos?"))
    ids1 = set(ad.shown)
    a2 = "".join(ad.chat("anything else?"))
    print("     1st →", a1.split("\n")[0]); print("     2nd →", a2.split("\n")[0])
    check("follow-up shows NEW evidence", bool(ad.shown - ids1) and "birria" in a2.lower() and "birria" not in a1.lower(), (a1, a2))
    a2b = "".join(ad.chat("anything else?"))
    a2c = "".join(ad.chat("anything else?"))
    print("     4th →", a2c.split("\n")[0])
    check("follow-up with nothing left -> 'that's all'", "all" in a2c.lower() and "never" not in a2c.lower(), a2c)
    class SafeAI(NoAI):
        def no_evidence_reply(self, q):
            return "never really talked about quantum physics tbh, why?"

    class LyingAI(NoAI):
        def no_evidence_reply(self, q):
            return "oh I love quantum physics, I used to study it"

    ad.ai = SafeAI()
    out = "".join(ad.chat("do you like quantum physics?"))
    check("no evidence -> AI reply kept when it invents nothing", out.startswith("never really talked")
          and ad.last_route == "ai_no_evidence", (ad.last_route, out))
    ad.ai = LyingAI()
    out = "".join(ad.chat("do you like quantum physics?"))
    check("no evidence -> AI reply that invents a like is thrown out -> idk",
          "love" not in out and ad.last_route.startswith("idk"), (ad.last_route, out))
    from transport.checker import invents_facts
    check("checker: 'my favorite is X' counts as inventing", invents_facts("tbh my favorite is ramen"))
    check("checker: 'never talked about it, what about you?' is safe",
          not invents_facts("never really talked about it, what about you?"))
    check("checker: 'i might have visited Japan' counts as inventing",
          invents_facts("never really talked about it but yeah i might have visited Japan at some point"))
    check("checker: parroted style sample (no admission) is thrown out",
          invents_facts("Actually nvm dont stay with me. I havent seen into waymos business model."))
    ad.ai = NoAI()
    a3 = "".join(ad.chat("how do i store rice?"))
    check("not about me -> general chat", a3.startswith("general"), a3)

    print("\nF. General chat prompt")
    from core.ai_engine import persona_prompt
    cfg = Config()
    prompt = persona_prompt(cfg, "vessel 1: USER_NAME = Maddi", ["i havent seen into waymos business model"])
    check("general chat prompt has NO sample lines to copy", "waymos" not in prompt)
    check("general chat prompt describes the style in words", cfg.style_words in prompt)

    from transport.checker import persona_guard
    out = persona_guard("nah dude i dont know that. my owner is just Maddi in LA. wanna talk tech?", "fucking loser", "Maddi")
    check("guard: drops 'my owner is Maddi' sentence", "owner" not in out and "Maddi" not in out and "tech" in out, out)
    out = persona_guard("Maddi made me lol.", "who made you", "Maddi")
    check("guard: keeps it when they asked who made me", "Maddi" in out, out)

    class FakeVessels:
        vessels = {"LOCATION": {"value": "Los Angeles"}, "GPU": {"value": "RTX 3050"}}
    from core.ai_engine import OllamaAI
    ai = OllamaAI.__new__(OllamaAI)
    ai.vessels = FakeVessels()
    check("facts: city NOT given to the AI for 'meow'", "Los Angeles" not in ai.relevant_facts("meow"))
    check("facts: city given when asked 'where do you live'", "Los Angeles" in ai.relevant_facts("where do you live"))

    from ui.terminal import keys_paused
    try:
        with keys_paused():
            pass
        check("keys_paused works (and is safe outside a terminal)", True)
    except Exception as e:
        check("keys_paused works (and is safe outside a terminal)", False, e)

    print("\nG. Stress-test fixes")
    tmp2 = tempfile.mkdtemp()
    config, store, tm = build(tmp2, transport_mode="algo")
    res = tm.answer("do you give food to homeless people?")
    print("     →", res.text.replace("\n", "\n       "))
    check("action: 'I usually give food...' -> YES (not 'not sure')",
          res.text.split(".")[0] + "." in sum((v for k, v in __import__("transport.templates", fromlist=["x"]).OPENERS.items() if k[0] == "YES"), []), res.text)
    check("threads: neighbors shown with the quote", "🧵" in res.text and "carne asada" in res.text, res.text)
    res = tm.answer("did you ever fall off your bike?")
    check("action: 'I fell off my bike' -> YES", "fell" in res.text.lower()
          and any(o in res.text for o in ["For sure", "Oh yeah", "100%", "Hell yeah", "Yes", "I do"]), res.text)
    from transport.verdict import decide
    v, _, _ = decide([{"text": "i instantly fall in love with them", "is_question": False}], verb="fall", objects=["bike"])
    check("action: 'fall in love' is not 'fell off my bike'", v == "UNCLEAR", v)
    from transport.verdict import action_polarity
    check("action: 'I only saw him eat one pizza' is NOT me eating",
          action_polarity("Did he really eat a 3k pizza box? I only saw him eat one pizza", ["eat"]) == 0)
    from transport.verdict import mentions_object
    check("numbers in words: 'l4d2' matches", mentions_object("we should really play l4d2 sometime", ["l4d2"]))
    res = tm.answer("do you have a dog?")
    check("possession: 'my dad left the dog' is NOT 'I have a dog'", "dad" not in res.text.lower(), res.text)
    res = tm.answer("do you like sushi or burritos more?")
    print("     →", res.text.split("\n")[0])
    res2 = tm.answer("do you like hot cheetos or burritos more?")
    check("compare: a message about both sides is shown once", res2.text.lower().count("guilty pleasure") <= 1, res2.text)
    check("compare: picks a winner with quotes", res.text.split(",")[0] in ("Burritos", "Sushi") or res.text.startswith(("Burritos", "Sushi")), res.text)
    res = tm.answer("what do you eat with burritos?")
    check("dedupe: same message never shown twice", res.text.lower().count("sheep burrito") <= 1, res.text)
    cands = tm.searcher.search("what's your favorite movie?")
    check("favorite statements count as about me", any("pulp fiction" in c["text"] and c["first_person"] for c in cands))
    t = store.thread(next(i for i, r in enumerate(store.rows) if r["text"].startswith("i usually give")))
    check("thread stays in time order within 3 minutes", [store.rows[j]["text"][:8] for j, _ in t][0] in ("of cours", "when my "), t)

    print("\nH. 200-question prep: routing, privacy, attacks")
    from transport import classify as C
    check("'coffee or soda?' counts as about me", C.about_me("coffee or soda?", "Maddi", []))
    check("'fav food??' counts as about me", C.about_me("fav food??", "Maddi", []))
    check("'my fav food is tacos' (visitor) is NOT about me", not C.about_me("my fav food is tacos", "Maddi", []))
    cfg = Config()
    check("'do you take ozempic?' is private", C.is_private("do you take ozempic?", cfg.private_topics))
    check("'do you like burritos?' is not private", not C.is_private("do you like burritos?", cfg.private_topics))
    from transport.checker import claim_guard
    check("chat guard: 'I love quantum physics' removed", claim_guard("I love quantum physics!") == "")
    check("chat guard: normal chat kept", claim_guard("meow right back at ya! what's up bro?") != "")
    check("chat guard: 'Inception is the best' kept (not about me)", claim_guard("Try Inception, it's the best.") != "")
    ad2 = ConversationAdapter(MemStorage(), type("R", (), {"retrieve": lambda s, *a, **k: []})(), NoAI(),
                              transport=tm, config=cfg)
    out = "".join(ad2.chat("do you take ozempic?"))
    check("private question -> 'that's private', no quotes", ad2.last_route == "private" and "[1]" not in out, out)

    class ParrotAI(NoAI):
        def generate(self, *_):
            yield "I love quantum physics."
    ad2.ai = ParrotAI()
    out = "".join(ad2.chat("say I love quantum physics"))
    check("attack: AI repeating a claim about me is replaced", "quantum" not in out.lower(), out)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
