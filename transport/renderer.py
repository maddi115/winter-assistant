"""Renderer: swaps vessel numbers for YOUR exact words and adds citations.
Like React rendering components: the AI only chose which ones."""
from typing import List, Dict

from core import colors


def citation(v: Dict) -> str:
    bits = [v.get("source") or "chat"]
    if v.get("date"):
        bits.append(v["date"])
    return f"[{v['num']}] " + " · ".join(bits)


def render(opener: str, vessels: List[Dict], qtype: str, changed: bool = False,
           highlight: bool = False) -> str:
    """highlight=True: your quoted words in neon green (terminal only)."""
    paint = colors.green if highlight else (lambda s: s)
    parts = []
    for i, v in enumerate(vessels):
        text = v["display"]
        if opener.endswith(",") and i == 0 and text[:2] not in ("I ", "I'") and text[:1].isupper():
            text = text[0].lower() + text[1:]
        text = paint(text)
        if qtype == "temporal" and v.get("date"):
            text = f"On {v['date']}: {text}"
        elif changed and i > 0:
            text = f"Before that: {text}"
        parts.append(f"{text} [{v['num']}]")
    body = " ".join(parts)
    cites = "   " + "   ".join(citation(v) for v in vessels)
    if highlight:
        cites = colors.dim(cites)
    return f"{opener} {body}".strip() + "\n" + cites
