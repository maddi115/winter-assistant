import lancedb
import json
import time
import uuid
from datetime import datetime
from sentence_transformers import SentenceTransformer
import os

class LanceDBConversationManager:
    def __init__(self, project_name, conversation_id=None):
        self.project = project_name
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.current_session = int(time.time())
        self.turn_number = 0

        print("🔄 Loading embedding model...")
        self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

        os.makedirs('lance_db', exist_ok=True)
        self.db = lancedb.connect('lance_db')

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
                "vector": [0.0] * 384
            }
            self.table = self.db.create_table('conversations', [schema])

        if conversation_id:
            turns = self.get_all_turns()
            if turns:
                self.turn_number = max(t['turn_number'] for t in turns) + 1

    def save_turn(self, user_msg, assistant_msg, elapsed_time):
        """Save conversation turn with embedding"""
        # Use first user message as title (no AI generation)
        if self.turn_number == 0:
            title = user_msg[:50]  # First 50 chars of user input
        else:
            try:
                result = self.table.search() \
                    .where(f"conversation_id = '{self.conversation_id}'") \
                    .limit(1).to_pandas()
                title = result.iloc[0]['title'] if len(result) > 0 else "Conversation"
            except:
                title = "Conversation"

        combined_text = f"user: {user_msg} | assistant: {assistant_msg}"
        vector = self.model.encode(combined_text).tolist()

        turn = {
            "conversation_id": self.conversation_id,
            "title": title,
            "timestamp": time.time(),
            "datetime": datetime.now().strftime("%Y-%m-%d %I:%M %p PT"),
            "session": self.current_session,
            "project": self.project,
            "turn_number": self.turn_number,
            "user": user_msg,
            "assistant": assistant_msg,
            "elapsed": elapsed_time,
            "vector": vector
        }

        self.table.add([turn])
        self.turn_number += 1

    def get_all_turns(self):
        """Get all turns from current conversation"""
        try:
            result = self.table.search() \
                .where(f"conversation_id = '{self.conversation_id}'") \
                .limit(1000).to_pandas()

            if len(result) == 0:
                return []

            turns = result.sort_values('turn_number').to_dict('records')
            return turns
        except:
            return []

    def get_recent_turns(self, n=5):
        """Get last N turns from current conversation"""
        turns = self.get_all_turns()
        return turns[-n:] if turns else []

    def search_conversations(self, query, limit=5, current_conversation_only=False):
        """Semantic search across conversations"""
        query_vector = self.model.encode(query).tolist()

        search = self.table.search(query_vector).limit(limit)

        if current_conversation_only:
            search = search.where(f"conversation_id = '{self.conversation_id}'")

        try:
            results = search.to_pandas().to_dict('records')
            return results
        except:
            return []

    def list_conversations(self, project=None):
        """List all unique conversations"""
        try:
            if project:
                result = self.table.search() \
                    .where(f"project = '{project}'") \
                    .limit(10000).to_pandas()
            else:
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
                        'turns': 0,
                        'last_updated': row['datetime']
                    }
                conversations[conv_id]['turns'] += 1

            return list(conversations.values())
        except Exception as e:
            print(f"Error listing conversations: {e}")
            return []
