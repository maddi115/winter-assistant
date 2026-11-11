#!/usr/bin/env python
"""Learn how I type from my imported messages -> memory/style.md

  python tools/learn_style.py

Only stats + word lists go in the file (and in the AI prompt) - never my real messages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from core import style


def main():
    config = Config.load()
    from storage.evidence_store import EvidenceStore
    store = EvidenceStore(config)
    if not store.ready:
        raise SystemExit("❌ No messages imported yet (python tools/import_chats.py ...)")
    s = style.write([r["text"] for r in store.rows], config.style_file)
    print(f"✅ learned from {s['messages']} of my messages -> {config.style_file}\n")
    print(Path(config.style_file).read_text())


if __name__ == "__main__":
    main()
