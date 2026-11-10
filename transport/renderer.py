"""Renderer: swaps vessel numbers for YOUR exact words and adds citations.
Like React rendering components: the AI only chose which ones."""
from typing import List, Dict

from core import colors


def citation(v: Dict) -> str:
    bits = [v.get("source") or "chat"]
    if v.get("date"):
        bits.append(v["date"])
    return f"[{v['num']}] " + " · ".join(bits)


def thread_block(num: int, v: Dict, lines, highlight: bool) -> str:
    """🧵 [1] twitch · 2025-07-05 14:02
          of course with rice
        → when my family folks make carne asada...   (the quote, green)
          i usually give food to homeless people only"""
    paint = colors.green if highlight else (lambda s: s)
    soft = colors.dim if highlight else (lambda s: s)
    when = (v.get("ts") or v.get("date") or "")[:16]
    head = f"   🧵 [{num}] " + " · ".join(b for b in [v.get("source") or "chat", when] if b)
    out = [soft(head) if highlight else head]
    from transport.packer import cosmetic
    for text, is_quote in lines:
        t = cosmetic(text)
        t = t if len(t) <= 110 else t[:107] + "..."
        out.append(f"    → {paint(t)}" if is_quote else "      " + soft(t))
    return "\n".join(out)


def render(opener: str, vessels: List[Dict], qtype: str, changed: bool = False,
           highlight: bool = False, threads: Dict = None, synth: str = None) -> str:
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
    threads = threads or {}
    plain = [v for v in vessels if v["num"] not in threads]
    cites = "   " + "   ".join(citation(v) for v in plain) if plain else ""
    if highlight and cites:
        cites = colors.dim(cites)
    blocks = [thread_block(v["num"], v, threads[v["num"]], highlight) for v in vessels if v["num"] in threads]
    tail = "\n".join(x for x in [cites] + blocks if x)
    if synth:
        # the AI's summary of my words (blue), with the real quotes right under it as proof
        head = "✨ " + (colors.blue(synth) if highlight else synth)
        proof = "   ↳ from my messages: " + body
        return head + "\n" + proof + ("\n" + tail if tail else "")
    return f"{opener} {body}".strip() + ("\n" + tail if tail else "")
