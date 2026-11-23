#!/usr/bin/env python
"""Re-embed Winter's stored vectors with the current embedding model.

Use this after the embedding model changes (or gets fixed), so old vectors and
new questions are made by the same model. Texts, dates, threads... stay the same:
only the "vector" column is recomputed from the text that's already stored.

  evidence       -> vector of the message text            (same as tools/import_chats.py)
  conversations  -> vector of "user: ... | assistant: ..." (same as storage/lancedb_storage.py)

Run from the winter-assistant folder. BACK UP storage/*.lance FIRST.
  python tools/reembed.py --dry-run     # shows what would change, writes nothing
  python tools/reembed.py               # re-embeds both tables

Stops if the model is loaded with mean pooling (the incomplete Qwen3 download),
so you can't re-embed with the broken model by accident. --force skips that check.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from storage.evidence_store import TABLE as EVIDENCE, has_table

CONVERSATIONS = "conversations"


def texts_for(name, df):
    if name == EVIDENCE:
        return df["text"].fillna("").astype(str).tolist()
    return [f"user: {u} | assistant: {a}" for u, a in zip(df["user"].fillna(""), df["assistant"].fillna(""))]


POOLING_FLAGS = {"lasttoken": "pooling_mode_lasttoken", "mean": "pooling_mode_mean_tokens",
                 "cls": "pooling_mode_cls_token", "max": "pooling_mode_max_tokens"}


def pooling_mode(embedder):
    """'lasttoken', 'mean', 'cls' or 'max' from the loaded sentence-transformers model (None if unknown)."""
    try:
        for module in embedder.model:
            if type(module).__name__ == "Pooling":
                for mode, flag in POOLING_FLAGS.items():
                    if getattr(module, flag, False):
                        return mode
    except Exception:
        pass
    return None


def reembed_table(db, name, embedder, dry_run=False, batch=64):
    """Recompute one table's vectors. Returns (rows, how much the vectors changed: avg cosine old vs new)."""
    if not has_table(db, name):
        print(f"   {name:14} not found, skipped")
        return 0, None
    table = db.open_table(name)
    df = table.to_pandas()
    if not len(df):
        print(f"   {name:14} empty, skipped")
        return 0, None
    t0 = time.time()
    new = embedder.encode_docs(texts_for(name, df), batch_size=batch).astype(np.float32)
    old = np.stack(df["vector"].to_numpy()).astype(np.float32)
    if old.shape[1] != new.shape[1]:
        raise SystemExit(f"❌ {name}: vector size changed {old.shape[1]} -> {new.shape[1]}, "
                         f"re-import with tools/import_chats.py --replace instead")
    old_n = old / (np.linalg.norm(old, axis=1, keepdims=True) + 1e-9)
    same = float((old_n * new).sum(axis=1).mean())
    print(f"   {name:14} {len(df):6} rows   {time.time() - t0:5.1f}s   old vs new similarity {same:.3f}"
          + ("   (dry run, nothing written)" if dry_run else ""))
    if not dry_run:
        df["vector"] = [v.tolist() for v in new]
        db.create_table(name, data=df, schema=table.schema, mode="overwrite")
    return len(df), same


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="compute and compare, write nothing")
    ap.add_argument("--force", action="store_true", help="re-embed even if the model uses mean pooling")
    ap.add_argument("--tables", default=f"{EVIDENCE},{CONVERSATIONS}")
    args = ap.parse_args()

    import lancedb
    from core.config import Config
    from core.embedder import get_embedder

    config = Config.load()
    embedder = get_embedder(config)
    mode = pooling_mode(embedder)
    print(f"\n🧠 {config.embedding_model} · pooling = {mode or 'unknown'} · {embedder.dim} dims")
    if "qwen3" in config.embedding_model.lower() and mode != "lasttoken" and not args.force:
        raise SystemExit("❌ Qwen3 should use last-token pooling, but this is loaded with "
                         f"'{mode}'. The model download is incomplete: fix that first (or use --force).")

    db = lancedb.connect(config.storage_path)
    print(f"📦 {config.storage_path}/\n")
    total = 0
    for name in [t.strip() for t in args.tables.split(",") if t.strip()]:
        n, _ = reembed_table(db, name, embedder, args.dry_run)
        total += n
    print(f"\n{'🔎 Dry run' if args.dry_run else '✅ Re-embedded'}: {total} rows\n")


if __name__ == "__main__":
    main()
