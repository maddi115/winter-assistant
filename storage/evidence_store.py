"""Evidence store: YOUR imported messages/notes (the source of truth).

Lives in LanceDB table 'evidence' (filled by tools/import_chats.py).
Only text, author, source and date are stored - no IPs, locations or user IDs.
The whole table is loaded into memory at startup so both searches
(vector + gradient) and the stasis math run fast on a home PC.
"""
from typing import List, Dict, Any

import lancedb
import numpy as np
import pandas as pd
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
        ("ts", pa.string()), ("channel", pa.string()),
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
        # private topics (health, address...) are never quotable
        from transport.classify import private_pattern
        pat = private_pattern(getattr(self.config, "private_topics", []))
        if pat is not None and len(df):
            df = df[~df["text"].str.contains(pat, na=False)].reset_index(drop=True)
        if not len(df):
            return
        self.vectors = np.stack(df["vector"].to_numpy()).astype(np.float32)
        for col in ("ts", "channel"):          # older imports don't have these
            if col not in df.columns:
                df[col] = ""
        self.rows = df.drop(columns=["vector"]).to_dict("records")
        self._build_threads(df)

    # ---------- threads ----------
    def _build_threads(self, df):
        """Order messages by time inside each channel, so a quote can show
        the messages right before and after it."""
        when = pd.to_datetime(df["ts"], errors="coerce")
        secs = (when - pd.Timestamp("1970-01-01")).dt.total_seconds()   # unit-safe
        self.secs = secs.fillna(-1).astype("int64").to_numpy()
        self.thread_pos = {}                   # row index -> (channel, position)
        self.channels = {}                     # channel -> [row indexes by time]
        order = np.argsort(self.secs, kind="stable")
        for i in order:
            if self.secs[i] < 0:
                continue
            ch = self.rows[i]["channel"]
            lst = self.channels.setdefault(ch, [])
            self.thread_pos[int(i)] = (ch, len(lst))
            lst.append(int(i))

    def thread(self, idx: int, window_sec: int = 180, max_each_side: int = 2):
        """[(row_index, is_the_quote)] in time order, same channel, within window_sec."""
        if idx not in getattr(self, "thread_pos", {}):
            return []
        ch, pos = self.thread_pos[idx]
        lst, t0 = self.channels[ch], self.secs[idx]
        before, after = [], []
        for j in range(pos - 1, max(-1, pos - 1 - max_each_side), -1):
            if t0 - self.secs[lst[j]] > window_sec:
                break
            before.insert(0, lst[j])
        for j in range(pos + 1, min(len(lst), pos + 1 + max_each_side)):
            if self.secs[lst[j]] - t0 > window_sec:
                break
            after.append(lst[j])
        same = lambda j: self.rows[j]["text"].strip().lower() == self.rows[idx]["text"].strip().lower()
        before = [j for j in before if not same(j)]
        after = [j for j in after if not same(j)]
        if not before and not after:
            return []
        return [(j, False) for j in before] + [(idx, True)] + [(j, False) for j in after]

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
