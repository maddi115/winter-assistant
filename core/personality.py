"""memory/personality.md -> how Winter talks (tone only, never facts).

Sections are plain '## name' headings. 'never say' lines become a hard filter;
everything else goes into the chat AI's prompt.
"""
import re
from pathlib import Path

_cache = {}


class Personality:
    def __init__(self, sections):
        self.sections = sections
        # any section named like "never say" / "banned words (never say)" is the hard filter
        self.never = [l.lower() for name, lines in sections.items() if "never" in name for l in lines]
        # "emojis" section: the only emojis/emotes I may use (optional, at most one per message)
        self.emojis = [w for name, lines in sections.items() if "emoji" in name for l in lines
                       for w in l.replace(",", " ").split() if not w.isalpha() or w[:1].isupper()]

    @property
    def prompt(self) -> str:
        """Short text for the AI (small models get confused by long prompts)."""
        out = []
        for name, lines in self.sections.items():
            if "never" in name or not lines:
                continue
            if "emoji" in name:
                out.append("emojis/emotes you may use (optional - most messages have none, never more than one): "
                           + " ".join(self.emojis))
                continue
            out.append(f"{name}: " + "; ".join(lines))
        if self.never:
            out.append("never say: " + "; ".join(f'"{n}"' for n in self.never))
        return "\n".join(out)[:1500]

    def breaks_rules(self, text: str) -> bool:
        return any(said(n, text) for n in self.never)


def said(phrase: str, text: str) -> bool:
    """Whole words only: 'sis' is banned, 'basis' is fine."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])", (text or "").lower()) is not None


def parse(text: str) -> Personality:
    sections, cur = {}, None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            cur = line[3:].strip().lower()
            sections[cur] = []
        elif line and not line.startswith("#") and cur:
            sections[cur].append(re.sub(r"^[-*]\s*", "", line))
    return Personality(sections)


def load(path="memory/personality.md") -> Personality:
    p = Path(path)
    if not p.exists():
        return Personality({})
    key = (str(p), p.stat().st_mtime)          # edits are picked up without restarting
    if key not in _cache:
        _cache.clear()
        _cache[key] = parse(p.read_text())
    return _cache[key]
