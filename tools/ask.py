#!/usr/bin/env python
"""Ask Winter questions without the chat UI, and see HOW each was answered.

  python tools/ask.py "do you like burritos?" "what games do you play?"
  python tools/ask.py --file my_30_questions.txt          # one question per line
  python tools/ask.py --file my_30_questions.txt --no-ai  # algorithm only

Prints each answer with its route (fact / algo / ai_pick / idk_* / general),
stability and confidence, then a summary: how many needed NO AI at all.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("questions", nargs="*")
    ap.add_argument("--file")
    ap.add_argument("--no-ai", action="store_true", help="transport_mode=algo, skip Ollama")
    args = ap.parse_args()

    qs = list(args.questions)
    if args.file:
        qs += [l.strip() for l in Path(args.file).read_text().splitlines() if l.strip()]
    if not qs:
        sys.exit("Give questions as arguments or --file questions.txt")

    config = Config.load()
    if args.no_ai:
        config.transport_mode = "algo"

    from storage.lancedb_storage import LanceDBStorage
    from adapters.conversation_adapter import ConversationAdapter
    from retrieval.hybrid_rag import HybridRAG
    from main import build_transport

    storage = LanceDBStorage(config)
    ai = None
    llm = None
    if not args.no_ai:
        from core.ai_engine import OllamaAI
        ai = OllamaAI(config)
        llm = ai.model
    transport, style = build_transport(config, storage, llm)
    if ai:
        ai.style = style

    class NoAI:
        def generate(self, *_):
            yield "(general chat - skipped with --no-ai)"

    adapter = ConversationAdapter(storage, HybridRAG(config), ai or NoAI(), transport=transport, config=config)
    # don't save test questions into your real chat history
    adapter._save = lambda *a, **k: None

    routes = Counter()
    for q in qs:
        text = "".join(adapter.chat(q)).split("\n\n⏱️")[0]
        d = adapter.last_debug
        routes[adapter.last_route] += 1
        print(f"\n❓ {q}\n🤖 {text}")
        print(f"   route={adapter.last_route}  stability={d.get('stability', '-')}  "
              f"confidence={d.get('confidence', '-')}  agreement={d.get('agreement', '-')}")

    no_ai = routes["fact"] + routes["algo"] + routes["algo_fallback"] + routes["idk_gate"] + routes["idk_empty"]
    print("\n" + "=" * 60)
    print(f"Routes: {dict(routes)}")
    print(f"Answered with NO AI at all: {no_ai}/{len(qs)} ({100 * no_ai // len(qs)}%)")


if __name__ == "__main__":
    main()
