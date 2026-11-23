"""Cabinet system: Winter's 4th result, read from localjev's fact cabinet.

localjev's learnfacts.py files lasting facts about you into drawers (one JSON per topic):

  ~/localjev/twitch/facts/
  ├── games.json      question, what you typed, learned facts (+ stasis score)
  ├── home.json ...
  ├── _unsure.json    never read here
  └── _private/       never read here

This file is self-contained: it does NOT use or change Winter's other searches
(vector, gradient, stasis gate). It only reads the drawers and picks one.

How a drawer is picked (two readings, both must agree):
  1. words    - question words found in the drawer (its name, question, facts)
  2. meaning  - question vs the drawer's question, with Winter's embedder
  score = 0.6 * meaning + 0.4 * words. Shown only if it passes cabinet_match_min,
  shares at least one word, and the meaning reading doesn't prefer another drawer.

Shown as its own block under Winter's answer, in a red -> orange dither.
Display only: nothing here is saved to chat history.

Try it:   python retrieval/cabinet_system.py "what games do you play?"
"""
import glob
import json
import os
import re
import sys
from typing import Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------- colors
# red -> orange, quantized with a 4x4 Bayer ordered dither (like localjev)
RED_ORANGE = [(200, 16, 16), (255, 36, 36), (255, 70, 10), (255, 110, 0), (255, 160, 20)]
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _rgb(c, bg=False):
    return f"\033[{48 if bg else 38};2;{c[0]};{c[1]};{c[2]}m"


def dither(text: str, row: int = 0) -> str:
    """Red -> orange gradient left to right, dithered."""
    if not COLOR or not text:
        return text
    n, out = max(1, len(text) - 1), []
    for i, ch in enumerate(text):
        t = i / n * (len(RED_ORANGE) - 1)
        base, frac = int(t), t - int(t)
        step = frac > (BAYER[row % 4][i % 4] + 0.5) / 16
        c = RED_ORANGE[min(base + step, len(RED_ORANGE) - 1)]
        out.append(_rgb(c, bg=True) + _rgb((25, 5, 0)) + ch)
    return "".join(out) + "\033[0m"


def dim(text: str) -> str:
    return f"\033[2m{text}\033[0m" if COLOR else text


def meter(score: float, width: int = 6) -> str:
    """Stasis bar in the same red -> orange."""
    cells = []
    for i in range(width):
        f = max(0.0, min(1.0, score * width - i))
        ch = " ░▒▓█"[round(f * 4)]
        cells.append((_rgb(RED_ORANGE[min(4, i * 5 // width)]) if COLOR else "") + ch)
    return "".join(cells) + ("\033[0m" if COLOR else "")


# ---------------------------------------------------------------- words
STOP = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with", "is", "are", "am",
    "was", "were", "be", "been", "do", "does", "did", "have", "has", "had", "i", "im", "me", "my", "you",
    "u", "ur", "your", "yours", "ya", "we", "it", "its", "that", "this", "what", "whats", "which", "who",
    "where", "when", "why", "how", "any", "some", "like", "really", "just", "so", "lol", "tell", "about",
    "kind", "type", "favorite", "fav", "fave", "can", "could", "would", "will", "there", "then", "now",
    "alot", "lot", "no", "yes", "not", "dont", "ever", "also", "too", "much", "many", "more", "most",
}


def stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def terms(text: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))
    return [stem(t) for t in toks if t not in STOP]


# ---------------------------------------------------------------- the cabinet
class CabinetSystem:
    def __init__(self, path: str, embedder=None, min_stasis: float = 0.25, match_min: float = 0.45,
                 private_topics=None):
        self.path = os.path.expanduser(path or "")
        self.embedder = embedder
        self.min_stasis = min_stasis
        self.match_min = match_min
        words = [re.escape(t.lower()) for t in (private_topics or []) if t.strip()]
        self.private = re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I) if words else None
        self.drawers: List[Dict] = []
        self.vectors = None
        self._load()

    @classmethod
    def from_config(cls, config, embedder=None):
        return cls(getattr(config, "cabinet_path", ""), embedder,
                   getattr(config, "cabinet_min_stasis", 0.25), getattr(config, "cabinet_match_min", 0.45),
                   getattr(config, "private_topics", []))

    @property
    def ready(self) -> bool:
        return bool(self.drawers)

    def _ok(self, text: str) -> bool:
        return bool(text.strip()) and not (self.private and self.private.search(text))

    def _load(self):
        if not self.path or not os.path.isdir(self.path):
            return
        # only the public drawers: files starting with "_" (_unsure.json) and the _private/ folder are skipped
        for p in sorted(glob.glob(os.path.join(self.path, "*.json"))):
            name = os.path.basename(p)[:-5]
            if name.startswith("_"):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:
                continue
            typed = d.get("typed_by_you", "") if self._ok(d.get("typed_by_you", "")) else ""
            facts = [r for r in d.get("facts", [])
                     if not r.get("old") and r.get("stasis", 0) >= self.min_stasis and self._ok(r.get("fact", ""))
                     and r.get("fact", "").lower() not in typed.lower()]
            facts.sort(key=lambda r: -r.get("stasis", 0))
            if not typed and not facts:
                continue
            words = " ".join([name, d.get("about", ""), d.get("question", ""), typed] + [r["fact"] for r in facts])
            self.drawers.append({"name": name, "question": d.get("question", ""), "about": d.get("about", ""),
                                 "typed": typed, "facts": facts[:3], "vocab": set(terms(words))})
        if self.embedder is not None and self.drawers:
            try:
                self.vectors = self.embedder.encode_docs(
                    [f"{d['question']} {d['about']}".strip() or d["name"] for d in self.drawers])
            except Exception:
                self.vectors = None

    # ---------- picking ----------
    def scores(self, question: str) -> List[Dict]:
        """Every drawer with its two readings, best first."""
        q = set(terms(question))
        meaning = np.zeros(len(self.drawers), dtype=np.float32)
        if self.vectors is not None:
            try:
                meaning = self.vectors @ self.embedder.encode_query(question)
            except Exception:
                pass
        rows = []
        for i, d in enumerate(self.drawers):
            shared = sorted(q & d["vocab"])
            words = len(shared) / len(q) if q else 0.0
            m = float(meaning[i])
            score = 0.6 * m + 0.4 * words if self.vectors is not None else words
            rows.append({"drawer": d, "words": words, "meaning": m, "score": score, "shared": shared})
        rows.sort(key=lambda r: -r["score"])
        return rows

    def pick(self, question: str) -> Optional[Dict]:
        if not self.ready:
            return None
        rows = self.scores(question)
        top = rows[0]
        if top["score"] < self.match_min or not top["shared"]:
            return None
        if self.vectors is not None:      # the meaning reading must not prefer another drawer
            best_m = max(r["meaning"] for r in rows)
            if top["meaning"] < best_m - 0.03:
                return None
        return top

    # ---------- the 4th result ----------
    def block(self, question: str) -> str:
        """The cabinet block shown under Winter's answer, or "" when no drawer clearly matches."""
        try:
            hit = self.pick(question)
        except Exception:
            return ""
        if not hit:
            return ""
        d = hit["drawer"]
        lines = [f"\n🗄️  {dim('cabinet · ' + d['name'] + '.json')}"]
        row = 0
        if d["typed"]:
            lines.append(f"   {dither(' ' + d['typed'] + ' ', row)}  {dim('✎ you typed')}")
            row += 1
        for r in d["facts"]:
            meta = f"{r.get('mentions', 0)}x · {r.get('days', 0)} days"
            lines.append(f"   {dither(' ' + r['fact'] + ' ', row)}  {meter(r.get('stasis', 0))} "
                         f"{dim(format(r.get('stasis', 0), '.2f') + ' · ' + meta)}")
            row += 1
        return "\n".join(lines)


# ---------------------------------------------------------------- try it from the terminal
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.config import Config
    question = " ".join(sys.argv[1:]) or "what games do you play?"
    config = Config.load()
    emb = None
    if "--words-only" not in sys.argv:
        from core.embedder import get_embedder
        emb = get_embedder(config)
    question = question.replace("--words-only", "").strip()
    cab = CabinetSystem.from_config(config, emb)
    if not cab.ready:
        sys.exit(f"cabinet not found or empty: {cab.path}")
    print(f"\n❓ {question}\n")
    for r in cab.scores(question):
        print(f"   {r['drawer']['name']:<12} score {r['score']:.2f}   meaning {r['meaning']:.2f}   "
              f"words {r['words']:.2f}   shared {', '.join(r['shared']) or '-'}")
    print(cab.block(question) or "\n   (no drawer clears the bar - no cabinet block)")
    print()
