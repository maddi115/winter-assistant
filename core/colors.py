"""Neon highlights in the terminal.

  neon pink      = pulled from a memory vessel (memory.txt / system.txt)
  neon green     = your own words from imported chat data
  blue gradient  = the AI summarized your words (synthesis, checked against the quotes)
  rainbow        = the AI's own words (no evidence / general chat)

Colors only show in a real terminal; saved history and files stay plain text.
"""
import re
import sys

PINK = "\033[1;38;2;255;16;240m"    # #FF10F0
GREEN = "\033[1;38;2;57;255;20m"    # #39FF14
DIM = "\033[2m"
RESET = "\033[0m"
ENABLED = sys.stdout.isatty()


def pink(s: str) -> str:
    return f"{PINK}{s}{RESET}" if ENABLED else s


def green(s: str) -> str:
    return f"{GREEN}{s}{RESET}" if ENABLED else s


def dim(s: str) -> str:
    return f"{DIM}{s}{RESET}" if ENABLED else s


def strip(s: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", s)


def _gradient(s: str, color_at) -> str:
    if not ENABLED or not s:
        return s
    n = max(1, len(s) - 1)
    out = []
    for i, ch in enumerate(s):
        if ch.isspace():
            out.append(ch)
            continue
        r, g, b = color_at(i / n)
        out.append(f"\033[1;38;2;{r};{g};{b}m{ch}")
    return "".join(out) + RESET


def rainbow(s: str) -> str:
    """The AI's own words."""
    import colorsys
    def at(t):
        r, g, b = colorsys.hsv_to_rgb(t * 0.85, 0.75, 1.0)
        return int(r * 255), int(g * 255), int(b * 255)
    return _gradient(s, at)


def blue(s: str) -> str:
    """The AI summarizing YOUR words."""
    def at(t):
        return int(30 + 20 * t), int(110 + 145 * t), 255     # deep blue -> cyan
    return _gradient(s, at)
