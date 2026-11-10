"""Pack search results into numbered VESSELS (whole messages) with
MICRO-VESSELS (single sentences, ids like 3.2) for long texts."""
import re
from typing import List, Dict

from retrieval.gradient import content_terms, stem, tokenize

LONG = 30  # words; longer texts get trimmed to their best sentence(s)


def cosmetic(text: str) -> str:
    """Capitals + punctuation only. Never changes, adds or removes real words."""
    t = re.sub(r"[\"']?@\w+[\s,:]*", " ", text.strip())   # @mentions (who I was talking to)
    t = t.strip(" \"'")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\bi\b", "I", t)
    t = re.sub(r"\bi(?=['’](m|ll|ve|d)\b)", "I", t)
    if t:
        t = t[0].upper() + t[1:]
        if t[-1] not in ".!?…)\"'" and t[-1].isalnum():
            t += "."
    return t


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


def best_micro(text: str, terms: List[str]):
    """Pick the sentence that mentions the question words (6-24 words preferred)."""
    sents = split_sentences(text)
    if len(sents) <= 1:
        return None
    def score(s):
        toks = {stem(w) for w in tokenize(s)}
        hits = sum(t in toks for t in terms)
        n = len(s.split())
        return (hits, 6 <= n <= 24, -abs(n - 14))
    i = max(range(len(sents)), key=lambda k: score(sents[k]))
    return i + 1, sents[i]


def pack(candidates: List[Dict], question: str, k: int) -> List[Dict]:
    terms = content_terms(question)
    vessels = []
    for n, c in enumerate(candidates[:k], 1):
        v = dict(c, num=n, vid=str(n), raw=c["text"], display=c["text"])
        if len(c["text"].split()) > LONG:
            micro = best_micro(c["text"], terms)
            if micro:
                v["vid"] = f"{n}.{micro[0]}"
                v["display"] = micro[1]
        v["display"] = cosmetic(v["display"])
        vessels.append(v)
    return vessels
