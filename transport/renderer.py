"""Renderer: swaps vessel numbers for YOUR exact words and adds citations.
Like React rendering components: the AI only chose which ones."""
from typing import List, Dict


def citation(v: Dict) -> str:
    bits = [v.get("source") or "chat"]
    if v.get("date"):
        bits.append(v["date"])
    return f"[{v['num']}] " + " · ".join(bits)


def render(opener: str, vessels: List[Dict], qtype: str, changed: bool = False) -> str:
    parts = []
    for i, v in enumerate(vessels):
        text = v["display"]
        if qtype == "temporal" and v.get("date"):
            text = f"On {v['date']}: {text}"
        elif changed and i > 0:
            text = f"Before that: {text}"
        parts.append(f"{text} [{v['num']}]")
    body = " ".join(parts)
    if opener.endswith(",") and body[:2] not in ("I ", "I'") and body[:1].isupper():
        body = body[0].lower() + body[1:]
    cites = "   " + "   ".join(citation(v) for v in vessels)
    return f"{opener} {body}".strip() + "\n" + cites
