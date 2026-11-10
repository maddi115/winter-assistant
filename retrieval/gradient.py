"""Gradient Proximity Search (from maddis-rag), cleaned up for Winter.

How it works:
  1. Pick the RAREST query word as the anchor.
  2. In each document, radiate left/right from the anchor with decaying strength.
  3. Finding another query word BOOSTS the strength (chaining).

Fix vs maddis-rag: the anchor itself now counts toward the score, and the score
is divided by the total rarity of the query, so it lands in 0..1.
(Before, a document with only the anchor word scored 0.)
Also: simple plural matching (burrito == burritos) and no chromadb dependency.
"""
import math
import re
from collections import Counter
from typing import List, Dict, Tuple

STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can',
    'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
    'what', 'which', 'who', 'when', 'where', 'why', 'how', 'me', 'my', 'mine', 'your',
    'yours', 'yourself', 'u', 'ur', 'ya', 'im', 'its', 'kind', 'type', 'sort', 'stuff',
    'thing', 'things', 'way', 'ways', 'lot', 'lots', 'much', 'many', 'some', 'any',
    'all', 'more', 'most', 'other', 'another', 'such', 'just', 'very', 'too', 'also',
    'even', 'really', 'quite', 'pretty', 'actually', 'basically', 'literally', 'ever',
    'about', 'think', 'tell', 'say', 'said', 'favorite', 'fav', 'like', 'love',
    'get', 'got', 'go', 'going', 'make', 'want', 'wanna', 'gonna', 'know', 'see', 'okay',
    'lol', 'yeah', 'yes', 'not', 'then', 'there', 'here', 'out', 'up', 'now', 'one', 'still',
}


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9']+", text.lower().replace("'", ""))


def stem(word: str) -> str:
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def content_terms(text: str) -> List[str]:
    """Meaningful query words, stemmed, in order, no duplicates."""
    out = []
    for w in tokenize(text):
        if w in STOP_WORDS or len(w) < 3:
            continue
        s = stem(w)
        if s not in out:
            out.append(s)
    return out


class GradientProximitySearch:
    def __init__(self, documents: List[str], window=20, base_boost=0.7,
                 min_weight=0.05, common_word_threshold=0.8):
        self.window = window
        self.base_boost = base_boost
        self.min_weight = min_weight
        self.common_limit = len(documents) * common_word_threshold
        self.doc_tokens = [[stem(w) for w in tokenize(d)] for d in documents]
        self.doc_freq = Counter()
        for toks in self.doc_tokens:
            self.doc_freq.update(set(toks))
        self.n_docs = max(1, len(documents))

    def _rarity(self, terms: List[str]) -> Dict[str, float]:
        return {t: math.log(self.n_docs / self.doc_freq[t]) + 1e-3
                for t in terms if self.doc_freq.get(t)}

    def _radiate(self, toks, anchor_pos, others, rarity) -> float:
        decay = self.window / 3
        max_r = max(rarity.values())
        found = {}
        visited = {anchor_pos}
        frontier = [(anchor_pos, 1.0)]
        while frontier:
            pos, strength = frontier.pop(0)
            if strength < self.min_weight:
                continue
            for off in range(1, self.window + 1):
                w = math.exp(-off / decay) * strength
                if w < self.min_weight:
                    break
                for p in (pos + off, pos - off):
                    if 0 <= p < len(toks) and p not in visited and toks[p] in others:
                        visited.add(p)
                        word = toks[p]
                        if w > found.get(word, 0):
                            found[word] = w
                        new_strength = min(1.0, strength + self.base_boost * rarity[word] / max_r)
                        if self.doc_freq[word] <= self.common_limit:
                            frontier.append((p, new_strength))
        return sum(found[w] * rarity[w] for w in found)

    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """Returns [(doc_index, score 0..1)] best first."""
        rarity = self._rarity(content_terms(query))
        if not rarity:
            return []
        anchor = max(rarity, key=rarity.get)
        others = set(rarity) - {anchor}
        total = sum(rarity.values())
        best = {}
        for i, toks in enumerate(self.doc_tokens):
            for pos, w in enumerate(toks):
                if w == anchor:
                    s = (rarity[anchor] + (self._radiate(toks, pos, others, rarity) if others else 0)) / total
                    if s > best.get(i, 0):
                        best[i] = s
        ranked = sorted(best.items(), key=lambda x: x[1], reverse=True)
        return [(i, min(1.0, s)) for i, s in ranked[:top_k]]
