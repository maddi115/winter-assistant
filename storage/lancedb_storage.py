"""LanceDB storage implementation"""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import lancedb
import uuid
import time
import os
from datetime import datetime
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer

from storage.base import BaseStorage
from core.errors import StorageError

class LanceDBStorage(BaseStorage):
    """LanceDB vector storage with embeddings"""

    def __init__(self, config):
        super().__init__(config)

        try:
            print("🔄 Loading embedding model...")
            self.model = SentenceTransformer(config.embedding_model, local_files_only=True)

            os.makedirs(config.storage_path, exist_ok=True)
            self.db = lancedb.connect(config.storage_path)

            try:
                self.table = self.db.open_table('conversations')
            except:
                schema = {
                    "conversation_id": "",
                    "title": "",
                    "timestamp": 0.0,
                    "datetime": "",
                    "session": 0,
                    "project": "",
                    "turn_number": 0,
                    "user": "",
                    "assistant": "",
                    "elapsed": 0.0,
                    "vector": [0.0] * 1024
                }
                self.table = self.db.create_table('conversations', [schema])

            self.conversation_id = None
            self.session = int(time.time())
            self.turn_number = 0

        except Exception as e:
            raise StorageError(f"LanceDB initialization failed: {e}")

    def _format_date_for_display(self, timestamp: float) -> str:
        """Format timestamp for clean display in list"""
        dt = datetime.fromtimestamp(timestamp)
        now = datetime.now()

        if dt.date() == now.date():
            return dt.strftime("%I:%M %p").lstrip('0')

        elif (now - dt).days == 1:
            return f"Yesterday {dt.strftime('%I:%M %p').lstrip('0')}"

        elif (now - dt).days < 7:
            return dt.strftime("%a %I:%M %p").lstrip('0')

        else:
            return dt.strftime("%b %d, %I:%M %p").lstrip('0')

    def list_all_conversations(self) -> List[Dict[str, Any]]:
        """List all conversations with metadata"""
        try:
            result = self.table.search().limit(10000).to_pandas()

            if len(result) == 0:
                return []

            conversations = {}
            for _, row in result.iterrows():
                conv_id = row['conversation_id']
                if conv_id not in conversations:
                    conversations[conv_id] = {
                        'conversation_id': conv_id,
                        'title': row['title'],
                        'project': row['project'],
                        'turn_count': 0,
                        'last_updated': '',
                        'timestamp': row['timestamp']
                    }
                conversations[conv_id]['turn_count'] += 1
                if row['timestamp'] > conversations[conv_id]['timestamp']:
                    conversations[conv_id]['timestamp'] = row['timestamp']

            for conv in conversations.values():
                conv['last_updated'] = self._format_date_for_display(conv['timestamp'])

            conv_list = list(conversations.values())
            conv_list.sort(key=lambda x: x['timestamp'], reverse=True)

            return conv_list
        except Exception as e:
            raise StorageError(f"List conversations failed: {e}")

    def load_conversation(self, conversation_id: str) -> None:
        """Load existing conversation by ID"""
        try:
            self.conversation_id = conversation_id

            turns = self.get_all_turns()
            if turns:
                self.turn_number = max(t['turn_number'] for t in turns) + 1
            else:
                self.turn_number = 0

        except Exception as e:
            raise StorageError(f"Load conversation failed: {e}")

    def save_turn(self, user_msg: str, ai_msg: str, metadata: Dict[str, Any]) -> None:
        """Save turn with embedding"""
        try:
            if self.conversation_id is None:
                self.conversation_id = str(uuid.uuid4())
                self.turn_number = 0

            # Use first user message as title (no AI generation)
            if self.turn_number == 0:
                title = user_msg[:50]  # First 50 chars of user input
            else:
                result = self.table.search() \
                    .where(f"conversation_id = '{self.conversation_id}'") \
                    .limit(1).to_pandas()
                title = result.iloc[0]['title'] if len(result) > 0 else "Conversation"

            combined = f"user: {user_msg} | assistant: {ai_msg}"
            vector = self.model.encode(combined).tolist()

            turn = {
                "conversation_id": self.conversation_id,
                "title": title,
                "timestamp": time.time(),
                "datetime": datetime.now().strftime("%Y-%m-%d %I:%M %p PT"),
                "session": self.session,
                "project": self.project,
                "turn_number": self.turn_number,
                "user": user_msg,
                "assistant": ai_msg,
                "elapsed": metadata.get('elapsed', 0.0),
                "vector": vector
            }

            self.table.add([turn])
            self.turn_number += 1

        except Exception as e:
            raise StorageError(f"Save failed: {e}")

    def get_recent(self, limit: int) -> List[Dict[str, Any]]:
        """Get recent turns from current conversation"""
        try:
            if self.conversation_id is None:
                return []

            result = self.table.search() \
                .where(f"conversation_id = '{self.conversation_id}'") \
                .limit(1000).to_pandas()

            if len(result) == 0:
                return []

            turns = result.sort_values('turn_number').to_dict('records')
            return turns[-limit:] if turns else []
        except Exception as e:
            raise StorageError(f"Get recent failed: {e}")

    def get_all_turns(self) -> List[Dict[str, Any]]:
        """Get all turns from current conversation"""
        try:
            if self.conversation_id is None:
                return []

            result = self.table.search() \
                .where(f"conversation_id = '{self.conversation_id}'") \
                .limit(1000).to_pandas()

            if len(result) == 0:
                return []

            return result.sort_values('turn_number').to_dict('records')
        except Exception as e:
            return []

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Semantic search across conversations"""
        try:
            if self.conversation_id is None:
                return []

            query_vector = self.model.encode(query).tolist()
            search = self.table.search(query_vector).limit(limit)
            search = search.where(f"conversation_id = '{self.conversation_id}'")

            results = search.to_pandas().to_dict('records')
            return results
        except Exception as e:
            raise StorageError(f"Search failed: {e}")
