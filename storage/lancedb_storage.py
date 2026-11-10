"""LanceDB storage for Winter's own conversations (one row per turn)."""
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any

import lancedb
import pyarrow as pa

from core.embedder import get_embedder
from storage.base import BaseStorage
from storage.evidence_store import has_table
from core.errors import StorageError


def _schema(dim: int) -> pa.Schema:
    return pa.schema([
        ("conversation_id", pa.string()), ("title", pa.string()),
        ("timestamp", pa.float64()), ("datetime", pa.string()),
        ("session", pa.int64()), ("project", pa.string()),
        ("turn_number", pa.int64()), ("user", pa.string()),
        ("assistant", pa.string()), ("elapsed", pa.float64()),
        ("vector", pa.list_(pa.float32(), dim)),
    ])


class LanceDBStorage(BaseStorage):
    """LanceDB vector storage with embeddings"""

    def __init__(self, config):
        super().__init__(config)
        try:
            self.embedder = get_embedder(config)
            self.db = lancedb.connect(config.storage_path)
            if has_table(self.db, 'conversations'):
                self.table = self.db.open_table('conversations')
            else:
                # real schema instead of a fake blank row
                self.table = self.db.create_table('conversations',
                                                  schema=_schema(self.embedder.dim))
            self.conversation_id = None
            self.session = int(time.time())
            self.turn_number = 0
        except Exception as e:
            raise StorageError(f"LanceDB initialization failed: {e}")

    # ---------- helpers ----------
    def _rows(self, where: str = None, limit: int = 100000):
        q = self.table.search()
        if where:
            q = q.where(where)
        df = q.limit(limit).to_pandas()
        # skip the blank placeholder row old versions created
        if len(df):
            df = df[df['conversation_id'] != ""]
        return df

    def _where_current(self) -> str:
        return f"conversation_id = '{self.conversation_id}'"

    @staticmethod
    def _format_date_for_display(timestamp: float) -> str:
        dt = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        if dt.date() == now.date():
            return dt.strftime("%I:%M %p").lstrip('0')
        if (now - dt).days == 1:
            return f"Yesterday {dt.strftime('%I:%M %p').lstrip('0')}"
        if (now - dt).days < 7:
            return dt.strftime("%a %I:%M %p").lstrip('0')
        return dt.strftime("%b %d, %I:%M %p").lstrip('0')

    # ---------- interface ----------
    def list_all_conversations(self) -> List[Dict[str, Any]]:
        try:
            df = self._rows()
            convs = {}
            for _, row in df.iterrows():
                c = convs.setdefault(row['conversation_id'], {
                    'conversation_id': row['conversation_id'], 'title': row['title'],
                    'project': row['project'], 'turn_count': 0,
                    'last_updated': '', 'timestamp': row['timestamp']})
                c['turn_count'] += 1
                c['timestamp'] = max(c['timestamp'], row['timestamp'])
            for c in convs.values():
                c['last_updated'] = self._format_date_for_display(c['timestamp'])
            return sorted(convs.values(), key=lambda x: x['timestamp'], reverse=True)
        except Exception as e:
            raise StorageError(f"List conversations failed: {e}")

    def load_conversation(self, conversation_id: str) -> None:
        try:
            self.conversation_id = conversation_id
            turns = self.get_all_turns()
            self.turn_number = max(t['turn_number'] for t in turns) + 1 if turns else 0
        except Exception as e:
            raise StorageError(f"Load conversation failed: {e}")

    def save_turn(self, user_msg: str, ai_msg: str, metadata: Dict[str, Any]) -> None:
        try:
            if self.conversation_id is None:
                self.conversation_id = str(uuid.uuid4())
                self.turn_number = 0
            if self.turn_number == 0:
                title = user_msg[:50]
            else:
                first = self._rows(self._where_current(), limit=1)
                title = first.iloc[0]['title'] if len(first) else "Conversation"

            vector = self.embedder.encode_docs([f"user: {user_msg} | assistant: {ai_msg}"])[0]
            self.table.add([{
                "conversation_id": self.conversation_id, "title": title,
                "timestamp": time.time(),
                "datetime": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
                "session": self.session, "project": self.project,
                "turn_number": self.turn_number, "user": user_msg,
                "assistant": ai_msg, "elapsed": float(metadata.get('elapsed', 0.0)),
                "vector": vector.tolist(),
            }])
            self.turn_number += 1
        except Exception as e:
            raise StorageError(f"Save failed: {e}")

    def get_recent(self, limit: int) -> List[Dict[str, Any]]:
        try:
            if self.conversation_id is None:
                return []
            df = self._rows(self._where_current(), limit=10000)
            turns = df.sort_values('turn_number').to_dict('records')
            return turns[-limit:]
        except Exception as e:
            raise StorageError(f"Get recent failed: {e}")

    def get_all_turns(self) -> List[Dict[str, Any]]:
        try:
            return self.get_recent(100000)
        except Exception:
            return []

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Semantic search across ALL conversations (not just the current one)."""
        try:
            if self.table.count_rows() == 0:
                return []
            qvec = self.embedder.encode_query(query).tolist()
            q = self.table.search(qvec)
            try:
                q = q.distance_type("cosine")
            except AttributeError:
                q = q.metric("cosine")
            df = q.where("conversation_id != ''").limit(limit).to_pandas()
            return df.to_dict('records')
        except Exception as e:
            raise StorageError(f"Search failed: {e}")
