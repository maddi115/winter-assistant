"""The ONLY place the AI touches your data: it picks numbers (multiple choice).

Forced JSON reply, so even a tiny model gives valid output.
Consensus: ask `votes` times and keep what the majority picked.
If the votes disagree, that's unstable -> "idk" (probability stasis, applied to the AI).
"""
from collections import Counter
from typing import List, Dict

from transport.checker import parse_reply, clean_picks

SCHEMA = {
    "type": "object",
    "properties": {
        "pick": {"type": "array", "items": {"type": "integer"}},
        "opener": {"type": "string"},
    },
    "required": ["pick", "opener"],
}


def build_messages(question, vessels, persona, agent_label, style, max_words, write_mode):
    style_block = "\n".join(f"- {s}" for s in style) or "- (none)"
    opener_rule = (f"a short line (max {max_words} words) that leads into the quotes"
                   if write_mode else f"a short opener (max {max_words} words), like 'oh for sure' or 'honestly'")
    system = (
        f"You are {agent_label}. You talk AS {persona}, in first person (I/me/my).\n"
        f"Below are numbered things {persona} really said.\n"
        f"Task 1: pick the numbers where {persona} is talking about the thing in the question. "
        f"If none of them answer it, return an empty list.\n"
        f"Task 2: write {opener_rule}. "
        f"Do NOT add facts, names or numbers. Do NOT repeat the quotes. Do NOT say 'you said'.\n"
        f"How {persona} types:\n{style_block}\n"
        f'Reply ONLY as JSON: {{"pick": [numbers], "opener": "text"}}'
    )
    listing = "\n".join(f"[{v['num']}] {v['display']}" for v in vessels)
    user = f"Question: {question}\n\n{listing}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def vote(llm, messages, n_vessels: int, votes: int) -> Dict:
    """Returns {'status': ok|none|split, 'picks': [...], 'openers': [...], 'agreement': 0..1, 'raw': [...]}."""
    votes = max(1, int(votes))
    temperature = 0.0 if votes == 1 else 0.7
    ballots, openers, raw = [], [], []
    for _ in range(votes):
        try:
            reply = llm.chat_json(messages, SCHEMA, max_tokens=80, temperature=temperature)
        except Exception as e:
            reply = f"error: {e}"
        raw.append(reply)
        picks, opener = parse_reply(reply)
        picks = clean_picks(picks, n_vessels)
        ballots.append(tuple(sorted(picks)))
        openers.append((tuple(sorted(picks)), opener))

    counts = Counter(p for b in ballots for p in b)
    majority = sorted(p for p, c in counts.items() if c > votes / 2)
    none_votes = sum(1 for b in ballots if not b)
    agreement = sum(1 for b in ballots if list(b) == majority) / votes

    if not majority:
        status = "none" if none_votes > votes / 2 else "split"
    else:
        status = "ok"
    # openers from ballots that agree with the majority come first
    ordered = [o for b, o in openers if list(b) == majority] + [o for b, o in openers if list(b) != majority]
    return {"status": status, "picks": majority, "openers": [o for o in ordered if o],
            "agreement": agreement, "raw": raw}
