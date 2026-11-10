#!/usr/bin/env python
"""Import your chats / notes into Winter's evidence table.

Examples (run from the winter-assistant folder):
  python tools/import_chats.py ../maddis-probability-stasisv2/data/chat_messages.csv --source twitch
  python tools/import_chats.py my_notes.txt --source notes
  python tools/import_chats.py chats.csv --source twitch --replace     # wipe + rebuild

Keeps ONLY: text, author, source, date. Every other column (IP, city,
user_id, client ids...) is dropped and never stored.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lancedb
import pandas as pd

from core.config import Config
from storage.evidence_store import TABLE, evidence_schema, has_table

TEXT_COLS = ["body_full", "body", "text", "message", "content"]
AUTHOR_COLS = ["login", "user", "username", "author", "sender"]
DATE_COLS = ["time", "timestamp", "date", "created_at", "datetime"]


def pick(cols, wanted, override=None):
    if override:
        return override
    for w in wanted:
        if w in cols:
            return w
    return None


def load_rows(path: Path, args, owner_handles):
    owner = {h.lower() for h in owner_handles}
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        tcol = pick(df.columns, TEXT_COLS, args.text_col)
        acol = pick(df.columns, AUTHOR_COLS, args.author_col)
        dcol = pick(df.columns, DATE_COLS, args.date_col)
        if not tcol:
            sys.exit(f"❌ No text column found. Columns: {list(df.columns)}")
        out = pd.DataFrame({
            "text": df[tcol].astype(str),
            "author": df[acol].astype(str) if acol else (owner_handles[0] if owner_handles else "me"),
            "date": pd.to_datetime(df[dcol], errors="coerce").dt.strftime("%Y-%m-%d") if dcol else "",
        })
        print(f"📄 {path.name}: text='{tcol}' author='{acol}' date='{dcol}' "
              f"(dropped {len(df.columns) - sum(bool(c) for c in (tcol, acol, dcol))} other columns)")
    else:
        raw = path.read_text(encoding="utf-8", errors="replace")
        parts = [p.strip() for p in raw.split("\n\n") if p.strip()]
        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
        out = pd.DataFrame({"text": parts,
                            "author": owner_handles[0] if owner_handles else "me",
                            "date": date})
    out["text"] = out["text"].str.strip()
    out = out[out["text"].str.split().str.len() >= 2]          # skip 1-word noise
    out = out[out["text"].str.lower() != "nan"]
    out["date"] = out["date"].fillna("")
    out["author"] = out["author"].fillna("")
    out["is_owner"] = out["author"].str.lower().isin(owner) if owner else True
    out["source"] = args.source
    return out.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--source", default="chat", help="label shown in citations, e.g. twitch")
    ap.add_argument("--replace", action="store_true", help="delete existing evidence first")
    ap.add_argument("--text-col"); ap.add_argument("--author-col"); ap.add_argument("--date-col")
    args = ap.parse_args()

    config = Config.load()
    path = Path(args.file)
    if not path.exists():
        sys.exit(f"❌ File not found: {path}")

    rows = load_rows(path, args, config.owner_handles)
    print(f"✅ {len(rows)} messages kept, {int(rows['is_owner'].sum())} are yours "
          f"(owner_handles = {config.owner_handles})")

    db = lancedb.connect(config.storage_path)
    if args.replace and has_table(db, TABLE):
        db.drop_table(TABLE)
        print("🗑️  Old evidence deleted")

    start_id = 0
    if has_table(db, TABLE):
        old = db.open_table(TABLE).to_pandas()[["id", "text", "date", "source"]]
        start_id = int(old["id"].max()) + 1 if len(old) else 0
        seen = set(zip(old["text"], old["date"], old["source"]))
        before = len(rows)
        rows = rows[[(t, d, s) not in seen for t, d, s in zip(rows["text"], rows["date"], rows["source"])]]
        print(f"↪️  Skipped {before - len(rows)} already imported")
    if not len(rows):
        print("Nothing new to import.")
        return

    from core.embedder import get_embedder
    emb = get_embedder(config)
    print(f"🔢 Embedding {len(rows)} messages (this can take a few minutes)...")
    vecs = emb.encode_docs(rows["text"].tolist())

    rows = rows.reset_index(drop=True)
    rows.insert(0, "id", range(start_id, start_id + len(rows)))
    rows["vector"] = [v.tolist() for v in vecs]
    rows = rows[["id", "text", "author", "is_owner", "source", "date", "vector"]]

    if has_table(db, TABLE):
        db.open_table(TABLE).add(rows)
    else:
        db.create_table(TABLE, data=rows, schema=evidence_schema(emb.dim))
    print(f"🎉 Imported {len(rows)} into LanceDB table '{TABLE}' at ./{config.storage_path}/")


if __name__ == "__main__":
    main()
