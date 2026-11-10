"""Instant replies that don't need the AI or my messages (like a real person would)."""
import random
import re

MEOW = re.compile(r"^\W*((m+e+o+w+|m+r+o+w+|m+e+w+|n+y+a+|purr+)\W*)+$", re.I)
MEOW_BACK = ["meow baow", "meow 🐱", "meow baow 🐱", "meoww 😺", "meow meow"]


def reflex(text: str):
    """-> reply text or None"""
    if MEOW.match((text or "").strip()):
        return random.choice(MEOW_BACK)
    return None
