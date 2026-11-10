"""Evidence store: YOUR imported messages/notes (the source of truth).

Lives in LanceDB table 'evidence' (filled by tools/import_chats.py).
Only text, author, source and date are stored - no IPs, locations or user IDs.
The whole table is loaded into memory at startup so both searches
(vector + gradient) and the stasis math run fast on a home PC.
"""
from typing import List, Dict, Any

import lancedb
import numpy as np
import pyarrow as pa

TABLE = "evidence"


def has_table(db, name: str) -> bool:
    try:
        res = db.list_tables()
        names = getattr(res, "tables", res)
        if getattr(res, "page_token", None):      # many tables: fall back to full listing
            names = db.table_names()
    except AttributeError:
        names = db.table_names()
    return name in list(names)


def evidence_schema(dim: int) -> pa.Schema:
    return pa.schema([
        ("id", pa.int64()), ("text", pa.string()), ("author", pa.string()),
        ("is_owner", pa.bool_()), ("source", pa.string()), ("date", pa.string()),
        ("vector", pa.list_(pa.float32(), dim)),
    ])


class EvidenceStore:
    def __init__(self, config, db=None):
        self.config = config
        self.db = db if db is not None else lancedb.connect(config.storage_path)
        self.rows: List[Dict[str, Any]] = []
        self.vectors = np.zeros((0, 1), dtype=np.float32)
        self.load()

    def load(self):
        if not has_table(self.db, TABLE):
            return
        df = self.db.open_table(TABLE).to_pandas()
        # Only the owner's own words can be spoken as "I"
        df = df[df["is_owner"]].reset_index(drop=True)
        if not len(df):
            return
        self.vectors = np.stack(df["vector"].to_numpy()).astype(np.float32)
        self.rows = df.drop(columns=["vector"]).to_dict("records")

    @property
    def ready(self) -> bool:
        return len(self.rows) > 0

    def texts(self) -> List[str]:
        return [r["text"] for r in self.rows]

    def vector_search(self, qvec: np.ndarray, k: int):
        """Returns [(row_index, cosine_similarity)] best first."""
        if not self.ready:
            return []
        sims = self.vectors @ qvec.astype(np.float32)
        k = min(k, len(sims))
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        return [(int(i), float(sims[i])) for i in top]

    def style_samples(self, n: int, seed: int = 7) -> List[str]:
        """A few real messages (6-20 words) so the AI's short lines sound like the owner."""
        pool = [r["text"] for r in self.rows if 6 <= len(r["text"].split()) <= 20]
        if not pool:
            return []
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(pool), size=min(n, len(pool)), replace=False)
        return [pool[i] for i in idx]
