"""Synthesis - the LAST RESORT before "idk".

Only used when the AI picker says no single quote answers the question by itself
("what do you eat with burritos?" -> the answer is spread over 3 quotes).
The AI writes ONE short first-person sentence from the picked quotes, with [n] citations.
The checker then makes sure every real word came from those quotes. If anything
doesn't check out, Winter shows the quotes alone, as before.
Shown in a BLUE gradient so you know it's a summary, with the quotes underneath as proof.
"""
import re
from typing import List, Dict, Optional

from retrieval.gradient import STOP_WORDS, stem, tokenize

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}

# small connecting words a summary may add
GLUE = {"usually", "or", "and", "also", "sometimes", "mostly", "with", "but", "too", "either", "both",
        "really", "stuff", "kind", "like", "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "to", "of", "in", "on", "at", "for", "from", "that", "this", "those", "these", "some", "pretty",
        "just", "mainly", "plus", "often", "even", "only", "when", "then", "than", "so", "not", "no",
        "yes", "yeah", "nah", "more", "most", "less", "ones", "one", "my", "me", "i", "im", "ive", "its",
        "it", "usually", "or", "maybe", "sorta", "kinda", "honestly", "tbh", "lol", "def", "all", "lot"}
BANNED = [r"\byou said\b", r"\bas an ai\b", r"\baccording to\b", r"\bthe quotes?\b", r"\bmessages?\b"]


def build_messages(question: str, shown: List[Dict], persona: str, agent_label: str, max_words: int):
    listing = "\n".join(f"[{v['num']}] {v['display']}" for v in shown)
    system = (
        f"You are {agent_label}, talking AS {persona} in first person.\n"
        f"Answer the question in ONE short sentence (max {max_words} words) using ONLY words from the numbered "
        f"things {persona} said. Put the number of each quote you used in brackets, like [1][3].\n"
        f"Do NOT add anything that isn't in them. Do NOT say 'you said' or mention quotes.\n"
        f'Reply ONLY as JSON: {{"answer": "..."}}'
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"Question: {question}\n\n{listing}"}]


def synthesize(llm, question, shown, persona, agent_label, max_words=25) -> str:
    import json
    raw = llm.chat_json(build_messages(question, shown, persona, agent_label, max_words),
                        SCHEMA, max_tokens=90, temperature=0.0)
    try:
        return str(json.loads(raw).get("answer", ""))
    except Exception:
        return raw


def check(answer: str, shown: List[Dict], question: str, persona: str, max_words: int = 25) -> Optional[str]:
    """Return the sentence if every real word is backed by the quotes, else None."""
    from transport.verdict import polarity
    s = re.sub(r"\s+", " ", (answer or "").strip().strip('"“”')).strip()
    if not s:
        return None
    low = s.lower()
    if any(re.search(b, low) for b in BANNED) or re.search(rf"\b{re.escape(persona.lower())}\b", low):
        return None
    cites = [int(n) for n in re.findall(r"\[(\d+)\]", s)]
    if not cites or any(n < 1 or n > len(shown) for n in cites):
        return None                                  # must cite real quotes
    words = re.sub(r"\[\d+\]", " ", s)
    if len(words.split()) > max_words + 5:
        return None
    # every sentence needs a citation
    for sent in re.split(r"(?<=[.!?])\s+", s):
        if len(sent.split()) >= 3 and not re.search(r"\[\d+\]", sent):
            return None
    # every real word must come from the quotes or the question
    allowed = set()
    for v in shown:
        allowed |= {stem(t) for t in tokenize(v.get("raw") or v["display"])}
    allowed |= {stem(t) for t in tokenize(question)}
    for t in tokenize(words):
        if t in STOP_WORDS or t in GLUE or len(t) < 3:
            continue
        if stem(t) not in allowed:
            return None
    # can't be more positive/negative than the evidence
    p = polarity(words)
    qp = [polarity(v.get("raw") or v["display"]) for v in shown]
    if (p > 0 and not any(x > 0 for x in qp)) or (p < 0 and not any(x < 0 for x in qp)):
        return None
    s = s[0].upper() + s[1:]
    return s
