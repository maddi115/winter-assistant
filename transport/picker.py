"""The ONLY place the AI touches your data: it picks numbers (multiple choice).

Forced JSON reply, so even a tiny model gives valid output.
Consensus: ask `votes` times and keep what the majority picked.
If the votes disagree, that's unstable -> "idk" (probability stasis, applied to the AI).
"""
import json
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
SCHEMA_STYLE = {
    "type": "object",
    "properties": {
        "pick": {"type": "array", "items": {"type": "integer"}},
        "style": {"type": "integer"},
        "direct": {"type": "boolean"},
    },
    "required": ["pick", "style", "direct"],
}


def build_messages(question, vessels, persona, agent_label, style, max_words, write_mode, styles=None):
    style_block = "\n".join(f"- {s}" for s in style) or "- (none)"
    if not write_mode and styles:
        # multiple choice again: even a tiny model can pick a number
        menu = "  ".join(f"{i}) {o}" for i, o in enumerate(styles, 1))
        system = (
            f"You are {agent_label}. You talk AS {persona}.\n"
            f"Below are numbered things {persona} really said.\n"
            f"Task 1: pick the numbers where {persona} is talking about the thing in the question. "
            f"If none of them answer it, return an empty list.\n"
            f"Task 2: pick the opener number that fits best: {menu}\n"
            f"Task 3: direct = true if ONE of your picked lines answers the question by itself, "
            f"false if the answer is spread over several lines.\n"
            f'Reply ONLY as JSON: {{"pick": [numbers], "style": number, "direct": true/false}}'
        )
        listing = "\n".join(f"[{v['num']}] {v['display']}" + (f"\n    (context: {v['context']})" if v.get("context") else "")
                             for v in vessels)
        return [{"role": "system", "content": system},
                {"role": "user", "content": f"Question: {question}\n\n{listing}"}]
    opener_rule = f"a short line (max {max_words} words) that leads into the quotes"
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


def vote(llm, messages, n_vessels: int, votes: int, styles=None) -> Dict:
    """Returns {'status': ok|none|split|error, 'picks': [...], 'openers': [...], 'agreement': 0..1, 'raw': [...]}."""
    votes = max(1, int(votes))
    temperature = 0.0 if votes == 1 else 0.7
    ballots, openers, raw, directs = [], [], [], []
    for _ in range(votes):
        try:
            reply = llm.chat_json(messages, SCHEMA_STYLE if styles else SCHEMA,
                                  max_tokens=80, temperature=temperature)
        except Exception as e:
            # timeout / Ollama down: don't wait through every vote
            return {"status": "error", "picks": [], "openers": [], "agreement": 0.0,
                    "raw": raw + [f"error: {e}"]}
        raw.append(reply)
        picks, opener = parse_reply(reply)
        if styles:   # opener chosen by number from the menu
            try:
                data = json.loads(reply)
                n = int(data.get("style", 0))
                directs.append(bool(data.get("direct", True)))
            except Exception:
                n = 0
                directs.append(True)
            opener = styles[n - 1] if 1 <= n <= len(styles) else ""
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
    needs_synth = bool(directs) and sum(1 for d in directs if not d) > len(directs) / 2
    return {"status": status, "picks": majority, "openers": [o for o in ordered if o],
            "agreement": agreement, "raw": raw, "needs_synth": needs_synth}
