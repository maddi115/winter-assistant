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


EVIDENCE = [
    ("i like eating burritos xxtra hot cheetos and kombucha thats my combo guilty pleasure", "agentmaddi", "2025-06-10"),
    ("i like eating my burrito de birria with cheese its awesome", "agentmaddi", "2025-07-01"),
    ("lordmironia no bro i eat burritos", "agentmaddi", "2025-06-20"),
    ("i wanna eat hot cheetos and cheap pizza", "madddyyyyi", "2025-06-12"),
    ("i wanna buy pizza", "agentmaddi", "2025-06-15"),
    ("sometimes i play video games while listening to the stream", "agentmaddi", "2025-07-03"),
    ("when i gwow up i wanna be a streamer and play video games all day", "agentmaddi", "2025-07-09"),
    ("i dont like sushi at all", "agentmaddi", "2025-06-01"),
    ("ok i tried sushi again and i love it now", "agentmaddi", "2025-08-01"),
    ("i fell really hard from my stupid bicycle", "madddyyyyi", "2025-06-05"),
    ("i love pizza so much", "somebody_else", "2025-06-06"),   # NOT the owner
] + [(f"random chat line number {w} about the stream and stuff", "agentmaddi", "2025-06-30")
     for w in ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
               "eleven", "twelve", "lol", "bro", "chat", "hello", "goodnight", "gg", "wow", "nice"]]


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
            "date": [d for _, _, d in EVIDENCE],
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
    check("'What's your name?' -> I'm Maddi (first person)", k and f.format_response(k, d).startswith("I'm Maddi"),
          f.format_response(k, d) if k else None)
    k, d = r.route("are you an ai?")
    check("'are you an ai?' -> honest AI label", k and "Maddi's AI" in f.format_response(k, d))

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
    res = tm.answer("do you like burritos?")
    print("     →", res.text.replace("\n", "\n       "))
    check("burritos -> YES with real quote", res.route == "algo" and ("burrito" in res.text.lower()), res.text)
    res = tm.answer("do you like pizza?")
    print("     →", res.text.replace("\n", "\n       "))
    check("pizza -> UNCLEAR (never a default YES)",
          any(o in res.text for o in ["not sure", "Not sure", "Kinda", "Hard to say"]), res.text)
    check("someone else's 'i love pizza' is never used", "so much" not in res.text)
    res = tm.answer("do you like sushi?")
    print("     →", res.text.replace("\n", "\n       "))
    check("sushi -> newest wins (changed mind)", res.text.lower().find("love it now") < res.text.lower().find("dont like")
          and "Before that" in res.text, res.text)
    res = tm.answer("do you like quantum physics?")
    print("     →", res.text)
    check("no evidence -> idk in first person", res.route.startswith("idk"), res.route)

    print("\nE. Transport model (AI picks numbers, 3 votes)")
    q = "what games do you play?"
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [1, 2], "opener": "honestly nothing specific"})] * 3,
                     winner_margin=0.9)      # force a close call so the AI is asked
    res = tm.answer(q)
    print("     →", res.text.replace("\n", "\n       "))
    check("votes agree -> AI picks used, real quotes shown", res.route == "ai_pick" and "video games" in res.text, res.text)
    check("AI opener kept after checking", res.text.lower().startswith("honestly nothing specific"), res.text)
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [1], "opener": "a"}), json.dumps({"pick": [3], "opener": "b"}),
                                   json.dumps({"pick": [], "opener": "c"})], winner_margin=0.9)
    res = tm.answer(q)
    check("votes split -> idk", res.route == "idk_votes", res.route)
    _, _, tm = build(tmp, ballots=[json.dumps({"pick": [9, 1], "opener": "In 1999 I did"})] * 3, winner_margin=0.9)
    res = tm.answer(q)
    check("bad number [9] dropped, bad opener replaced by template",
          res.route == "ai_pick" and "1999" not in res.text and "[2]" not in res.text, res.text)

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
    a3 = "".join(ad.chat("how do i store rice?"))
    check("not about me -> general chat", a3.startswith("general"), a3)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
