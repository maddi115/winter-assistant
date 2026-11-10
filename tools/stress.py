#!/usr/bin/env python
"""Stress test: run many questions, write ONE ROW per question to a CSV.

  python tools/stress.py stress_questions.txt              -> stress_results.csv
  python tools/stress.py stress_questions.txt --no-ai      (algorithm only)

Question file: one per line, optionally "category | question".
Lines starting with # are skipped. Order matters for follow-ups ("anything else?").
"""
import argparse
import csv
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from core import colors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--out", default="stress_results.csv")
    ap.add_argument("--no-ai", action="store_true")
    args = ap.parse_args()

    rows = []
    for line in Path(args.file).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cat, _, q = line.partition("|") if "|" in line else ("", "", line)
        rows.append((cat.strip() or "misc", q.strip()))

    config = Config.load()
    if args.no_ai:
        config.transport_mode = "algo"
    colors.ENABLED = False

    from storage.lancedb_storage import LanceDBStorage
    from adapters.conversation_adapter import ConversationAdapter
    from retrieval.hybrid_rag import HybridRAG
    from main import build_transport

    storage = LanceDBStorage(config)
    ai, llm = None, None
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
    adapter._save = lambda *a, **k: None          # don't fill your chat history with tests

    out = []
    for n, (cat, q) in enumerate(rows, 1):
        t0 = time.time()
        try:
            text = colors.strip("".join(adapter.chat(q))).split("\n\n⏱️")[0]
        except Exception as e:
            text = f"ERROR: {e}"
        secs = time.time() - t0
        first = text.strip().split("\n")[0]
        d = adapter.last_debug or {}
        out.append({
            "n": n, "category": cat, "question": q, "route": adapter.last_route,
            "answer": first[:300], "quotes": len(set(re.findall(r"\[(\d)\]", first))),
            "stability": d.get("stability", ""), "confidence": d.get("confidence", ""),
            "agreement": round(d["agreement"], 2) if isinstance(d.get("agreement"), float) else "",
            "seconds": round(secs, 2),
        })
        print(f"{n:3}/{len(rows)} {adapter.last_route or '?':15} {secs:5.1f}s  {q[:60]}", flush=True)

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    print("\n" + "=" * 70)
    by_cat = defaultdict(Counter)
    for r in out:
        by_cat[r["category"]][r["route"]] += 1
    for cat, c in by_cat.items():
        print(f"{cat:14} " + "  ".join(f"{k}={v}" for k, v in c.most_common()))
    secs = [r["seconds"] for r in out]
    no_ai = sum(1 for r in out if r["route"] in ("fact", "algo", "algo_fallback", "idk_gate", "idk_empty"))
    print(f"\nNo AI at all: {no_ai}/{len(out)} ({100 * no_ai // len(out)}%)   "
          f"avg {sum(secs) / len(secs):.1f}s   slowest {max(secs):.1f}s")
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()
