#!/usr/bin/env python
"""Offline tests for the cabinet system (Winter's 4th result).

No Ollama, no embedding download, no real cabinet needed: builds a fake cabinet in a temp folder.
Run from the winter-assistant folder:   python tests/test_cabinet_system.py
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import retrieval.cabinet_system as C
from retrieval.cabinet_system import CabinetSystem, terms
from transport import TransportResult

PASSED, FAILED = [], []


def check(name, cond, info=""):
    (PASSED if cond else FAILED).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + ("" if cond else f"   -> {info}"))


class FakeEmbedder:
    """Bag-of-words hashing vectors: shared words -> similar vectors."""
    dim = 128

    def _vec(self, text):
        v = np.zeros(self.dim, dtype=np.float32)
        for w in terms(text):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode_docs(self, texts):
        return np.stack([self._vec(t) for t in texts])

    def encode_query(self, text):
        return self._vec(text)


def fact(text, stasis, old=False):
    return {"fact": text, "mentions": 3, "days": 3, "first": "2025-06-01", "last": "2025-08-01",
            "stasis": stasis, "old": old}


DRAWERS = {
    "games": {"question": "what games do you play?", "about": "what video games you play or like",
              "typed_by_you": "racing games and puzzle games", "facts": [fact("i play chess online", 0.4)]},
    "home": {"question": "where are you from?", "about": "where you live or are from",
             "typed_by_you": "", "facts": [fact("i live in springfield", 0.56), fact("i live near the beach", 0.1)]},
    "food": {"question": "what do you like to eat?", "about": "what you eat and drink", "typed_by_you": "",
             "facts": [fact("i eat tacos", 0.5), fact("i used to eat cereal", 0.6, old=True),
                       fact("i take medsecret pills with food", 0.5)]},
    "work": {"question": "what do you do for work?", "about": "what work or jobs you do", "typed_by_you": "",
             "facts": [fact("i have one job", 0.1)]},   # below the stasis bar -> drawer is empty
}


def make_cabinet():
    tmp = tempfile.mkdtemp()
    for name, d in DRAWERS.items():
        with open(os.path.join(tmp, f"{name}.json"), "w") as f:
            json.dump(dict(d, drawer=name, answer=""), f)
    with open(os.path.join(tmp, "_unsure.json"), "w") as f:
        json.dump([fact("i play the unsure game", 0.9)], f)
    os.makedirs(os.path.join(tmp, "_private"))
    with open(os.path.join(tmp, "_private", "health.json"), "w") as f:
        json.dump([fact("i have a private thing", 0.9)], f)
    return tmp


def main():
    C.COLOR = False
    path = make_cabinet()
    cab = CabinetSystem(path, FakeEmbedder(), min_stasis=0.25, match_min=0.35, private_topics=["medsecret"])

    print("\n🗄️  Loading")
    names = sorted(d["name"] for d in cab.drawers)
    check("loads public drawers only", names == ["food", "games", "home"], names)
    every = " ".join(d["typed"] + " " + " ".join(r["fact"] for r in d["facts"]) for d in cab.drawers)
    check("never reads _private/", "private thing" not in every, every)
    check("never reads _unsure.json", "unsure game" not in every, every)
    check("skips 'used to' facts", "cereal" not in every, every)
    check("skips facts below the stasis bar", "near the beach" not in every and "one job" not in every, every)
    check("private_topics filter hides a fact", "medsecret" not in every, every)

    print("\n🎯 Picking a drawer")
    from retrieval.cabinet_system import stem
    check("stem: games -> game (not 'gam')", stem("games") == "game" and stem("game") == "game", stem("games"))
    check("stem: playing/played/boxes/burritos", [stem(w) for w in ["playing", "played", "boxes", "burritos"]]
          == ["play", "play", "box", "burrito"], [stem(w) for w in ["playing", "played", "boxes", "burritos"]])
    for q, want in [("what games do you play?", "games"), ("what game do you play", "games"),
                    ("what video games u play", "games"),
                    ("where are you from?", "home"), ("where do you live", "home"),
                    ("what do you like to eat?", "food")]:
        hit = cab.pick(q)
        got = hit["drawer"]["name"] if hit else None
        check(f"'{q}' -> {want}", got == want, got)
    for q in ["how do i cook rice?", "meow", "what time is it", "do you like the weather today"]:
        check(f"'{q}' -> no drawer", cab.pick(q) is None, cab.pick(q) and cab.pick(q)["drawer"]["name"])

    print("\n🖼️  The block")
    b = cab.block("what games do you play?")
    check("block names the drawer file", "cabinet · games.json" in b, b)
    check("block shows what you typed first", b.index("racing games") < b.index("chess"), b)
    check("block shows learned facts with stasis", "0.40" in b and "3x · 3 days" in b, b)
    check("no match -> empty block", cab.block("how do i cook rice?") == "")
    C.COLOR = True
    colored = cab.block("what games do you play?")
    check("red-orange dither colors in a terminal", "\033[48;2;" in colored and "\033[48;2;255;36;36m" in colored)
    C.COLOR = False

    print("\n🚫 Off switches")
    check("missing folder -> off", not CabinetSystem("/nope/does/not/exist").ready)
    check("missing folder -> empty block", CabinetSystem("/nope").block("what games do you play?") == "")
    words_only = CabinetSystem(path, None, match_min=0.35)
    hit = words_only.pick("what games do you play?")
    check("works without an embedder (words only)", hit and hit["drawer"]["name"] == "games")

    print("\n🔌 Hooked into Winter (4th result, display only)")
    from core.config import Config
    from adapters.conversation_adapter import ConversationAdapter

    class FakeTransport:
        def answer(self, question, exclude=frozenset(), tone_source=None):
            return TransportResult("Okay so, I play chess. [1]", "algo", [1], {})

    class FakeStorage:
        saved = []
        def save_turn(self, u, r, meta):
            self.saved.append(r)

    config = Config()
    storage = FakeStorage()
    ad = ConversationAdapter(storage, rag=None, ai=None, transport=FakeTransport(), config=config, cabinet=cab)
    out = "".join(ad.chat("what games do you play?"))
    check("Winter's answer comes first, cabinet block under it",
          out.index("I play chess") < out.index("cabinet · games.json"), out)
    check("cabinet block is not saved to history", "cabinet" not in storage.saved[-1], storage.saved[-1])
    out2 = "".join(ad.chat("what else?"))
    check("follow-up 'what else?' doesn't repeat the cabinet", "cabinet" not in out2, out2)
    ad_off = ConversationAdapter(FakeStorage(), rag=None, ai=None, transport=FakeTransport(), config=config)
    check("no cabinet -> Winter unchanged", "cabinet" not in "".join(ad_off.chat("what games do you play?")))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
