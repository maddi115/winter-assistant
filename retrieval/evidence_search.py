"""Two searches over your evidence, merged and reranked. No AI involved.

  1. Vector search  (meaning)      - Qwen3 embeddings
  2. Gradient search (rare words)  - from maddis-rag
  3. Merge by RANK (reciprocal rank fusion), not raw score,
     because the two scores are on different scales.
  4. Rerank: 0.6 * meaning + 0.4 * keywords  (from stasisv2; rare words weigh more),
     small bonus when BOTH searches found it, and when it's first person ("I", "my").
"""
from typing import List, Dict, Any, Set

from retrieval.gradient import GradientProximitySearch, content_terms, stem, tokenize

RRF_K = 60
POOL = 15


FIRST_PERSON = {"i", "im", "my", "me", "mine", "ive", "id", "ill", "myself"}


def keyword_score(terms: List[str], text: str, weights: Dict[str, float] = None) -> float:
    """Share of the question's words found in the text; rare words count more."""
    if not terms:
        return 0.0
    toks = {stem(w) for w in tokenize(text)}
    w = weights or {t: 1.0 for t in terms}
    total = sum(w.get(t, 0.0) for t in terms) or 1.0
    return sum(w.get(t, 0.0) for t in terms if t in toks) / total


class EvidenceSearch:
    def __init__(self, store, embedder, k: int = 20):
        self.store = store
        self.embedder = embedder
        self.k = k
        self.gradient = GradientProximitySearch(store.texts()) if store.ready else None

    def search(self, question: str, exclude: Set[int] = frozenset()) -> List[Dict[str, Any]]:
        if not self.store.ready:
            return []
        qvec = self.embedder.encode_query(question)
        terms = content_terms(question)
        weights = self.gradient._rarity(terms) if self.gradient else {}
        anchor = max(weights, key=weights.get) if weights else None

        vec_hits = self.store.vector_search(qvec, self.k + len(exclude))
        grad_hits = self.gradient.search(question, self.k + len(exclude)) if self.gradient else []

        cands = {}
        for source, hits in (("vector", vec_hits), ("gradient", grad_hits)):
            rank = 0
            for idx, score in hits:
                if idx in exclude:
                    continue
                rank += 1
                c = cands.setdefault(idx, {"idx": idx, "found_by": set(), "rrf": 0.0, "grad": 0.0})
                c["found_by"].add(source)
                c["rrf"] += 1.0 / (RRF_K + rank)
                if source == "gradient":
                    c["grad"] = score

        pool = sorted(cands.values(), key=lambda c: c["rrf"], reverse=True)[:POOL]
        for c in pool:
            row = self.store.rows[c["idx"]]
            c.update(row)                                  # text, date, source, author, id
            c["vector"] = self.store.vectors[c["idx"]]
            c["sem"] = float(self.store.vectors[c["idx"]] @ qvec)
            toks = {stem(w) for w in tokenize(row["text"])}
            c["kw"] = keyword_score(terms, row["text"], weights)
            c["has_anchor"] = anchor is not None and anchor in toks
            c["first_person"] = bool(FIRST_PERSON & set(tokenize(row["text"])))
            c["is_question"] = row["text"].strip().endswith("?")
            c["both"] = len(c["found_by"]) == 2
            c["combo"] = (0.6 * c["sem"] + 0.4 * c["kw"]
                          + (0.05 if c["both"] else 0.0)
                          + (0.05 if c["first_person"] else 0.0)    # talking about myself
                          - (0.10 if c["is_question"] else 0.0))    # asking someone else
        pool.sort(key=lambda c: (c["combo"], c["rrf"]), reverse=True)
        return pool
