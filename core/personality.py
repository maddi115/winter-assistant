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
        self.never = [l.lower() for l in sections.get("never say", [])]

    @property
    def prompt(self) -> str:
        """Short text for the AI (small models get confused by long prompts)."""
        out = []
        for name, lines in self.sections.items():
            if name == "never say" or not lines:
                continue
            out.append(f"{name}: " + "; ".join(lines))
        if self.never:
            out.append("never say: " + "; ".join(f'"{n}"' for n in self.never))
        return "\n".join(out)[:1500]

    def breaks_rules(self, text: str) -> bool:
        low = (text or "").lower()
        return any(n in low for n in self.never)


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
