"""Router - answers a few EXACT questions instantly from memory.txt / system.txt.

Patterns match the WHOLE question (after lowercasing and removing punctuation),
so "how do i store rice?" no longer gets hijacked by the word "store".
"""
import re
from typing import Optional, Dict, Tuple

YOU = r"(you|u)"
YOUR = r"(your|ur)"
WHATS = r"(whats|what is)"


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("'", "")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # drop greetings in front: "hi whos ur owner" -> "whos ur owner"
    while True:
        new = re.sub(r"^(hi+|hey+|hello|yo+|sup|ok|okay|so|bro|um+|uh+)\b\s*", "", text)
        if new == text:
            return text
        text = new


class Router:
    """Routes exact questions to stored facts; everything else returns (None, None)."""

    # Asked by the owner about themselves ("my ...") -> answered as "your ..."
    MY_PATTERNS = {
        'USER_NAME': [rf"^{WHATS} my name( again)?$", r"^who am i$", rf"^do {YOU} know my name$"],
        'PROJECT': [r"^what am i (working on|building)( right now| rn)?$", rf"^{WHATS} my project$"],
        'GPU': [r"^(what|which) (gpu|graphics card) do i have$", rf"^{WHATS} my (gpu|graphics card)$",
                r"^how much vram do i have$"],
        'LOCATION': [r"^where am i$", rf"^{WHATS} my location$", r"^what city am i in$",
                     r"^where do i live$"],
    }

    # Asked about the agent ("your ...") -> answered in first person
    PATTERNS = {
        'AI_NAME': [rf"^{WHATS} {YOUR} name( again)?$", rf"^who (are|r) {YOU}$"],
        'LOCATION': [rf"^where (are|r) {YOU}( from| based| located| at)?$",
                     rf"^where do {YOU} live$"],
        'PROJECT': [rf"^what (are|r) {YOU} (working on|building)( right now| rn)?$",
                    rf"^{WHATS} {YOUR} project$"],
        'GPU': [rf"^(what|which) (gpu|graphics card) (do|does) {YOU} have$",
                rf"^{WHATS} {YOUR} (gpu|graphics card)$",
                rf"^how much vram (do|does) {YOU} have$"],
        'AI_DISCLOSURE': [rf"^(are|r) {YOU} (an |a )?(ai|bot|robot|real|human|a real person)$"],
        'AI_OWNER': [rf"^(who|whos|whose|who is|who s) {YOUR} (owner|creator|maker|dev|developer|boss)$",
                     rf"^who (made|built|created|owns|programmed|coded|trained) {YOU}$",
                     rf"^who do {YOU} belong to$", rf"^who {YOU} belong to$"],
        'AI_MODEL': [rf"^what (model|llm) (are|r) {YOU}( running| using| on)?$"],
        'AI_STORAGE': [rf"^what database do {YOU} use$"],
        'AI_EMBEDDING': [rf"^what embedding model do {YOU} use$"],
    }
    # which stored fact answers each pattern group
    FACT_FOR = {'AI_DISCLOSURE': 'AI_NAME', 'AI_OWNER': 'AI_NAME'}

    def __init__(self, vessels_obj):
        self.vessels = vessels_obj.vessels
        self.system_facts = vessels_obj.system_facts

    def route(self, user_input: str) -> Tuple[Optional[str], Optional[Dict]]:
        q = normalize(user_input)
        for key, patterns in self.MY_PATTERNS.items():
            if any(re.match(p, q) for p in patterns) and key in self.vessels:
                return key, dict(self.vessels[key], perspective="owner")
        for key, patterns in self.PATTERNS.items():
            if any(re.match(p, q) for p in patterns):
                fact_key = self.FACT_FOR.get(key, key)
                data = self.vessels.get(fact_key) or self.system_facts.get(fact_key)
                if data:
                    return key, data
        return None, None
