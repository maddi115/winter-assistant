"""Conversation adapter - orchestrates core + storage + RAG"""
import time
from typing import Dict, Any, Iterator
from rich.console import Console

from core.interfaces import StorageInterface, RAGInterface, AIInterface
from core.errors import StorageError, RAGError, AIError
from core.memory_injector import MemoryInjector

console = Console()

class ConversationAdapter:
    """Orchestrates conversation flow with error handling"""

    def __init__(self, storage: StorageInterface, rag: RAGInterface, ai: AIInterface):
        self.storage = storage
        self.rag = rag
        self.ai = ai
        self.injector = MemoryInjector()

    def chat(self, user_input: str) -> Dict[str, Any]:
        """Handle complete chat interaction"""
        start_time = time.time()

        # ROUTER: Check if this is a simple fact question
        fact_key, fact_data = self.injector.route(user_input)
        
        if fact_key and fact_data:
            # Direct fact retrieval - bypass AI entirely
            response = self.injector.format_response(fact_key, fact_data)
            elapsed = time.time() - start_time
            
            try:
                self.storage.save_turn(user_input, response, {'elapsed': elapsed})
            except StorageError as e:
                print(f"\n⚠️  Storage failed: {e}")
            
            console.print(response)
            yield ""
            yield f"\n\n⏱️  {elapsed:.2f}s\n"
            return

        # Complex question - use AI with RAG (no citations, just context)
        try:
            context = self.rag.retrieve(user_input, self.storage, limit=6)
        except RAGError as e:
            print(f"⚠️  RAG failed, using simple retrieval: {e}")
            context = self.storage.get_recent(5)
        except Exception as e:
            print(f"⚠️  Retrieval error: {e}")
            context = []

        try:
            response_chunks = []
            for chunk in self.ai.generate(user_input, context):
                response_chunks.append(chunk)
                yield chunk

            response = ''.join(response_chunks)
            elapsed = time.time() - start_time

            try:
                self.storage.save_turn(user_input, response, {'elapsed': elapsed})
            except StorageError as e:
                print(f"\n⚠️  Storage failed: {e}")

            yield f"\n\n⏱️  {elapsed:.2f}s\n"

        except AIError as e:
            yield f"\n❌ AI Error: {e}\n"
        except Exception as e:
            yield f"\n❌ Unexpected error: {e}\n"

    def search_history(self, query: str, limit: int = 5) -> list:
        """Search conversation history"""
        try:
            return self.storage.search(query, limit)
        except Exception as e:
            print(f"⚠️  Search failed: {e}")
            return []

    def get_recent_turns(self, limit: int = 10) -> list:
        """Get recent conversation history"""
        try:
            return self.storage.get_recent(limit)
        except Exception as e:
            print(f"⚠️  History retrieval failed: {e}")
            return []
