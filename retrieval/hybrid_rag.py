"""Hybrid RAG over Winter's own past chats: recent turns + semantic hits.

Each side gets its OWN slots, so semantic hits are never cut off by recency.
"""
from typing import List, Dict, Any

from retrieval.base import BaseRAG
from core.interfaces import StorageInterface
from core.errors import RAGError


def _key(turn):
    return f"{turn.get('conversation_id', '')}_{turn.get('turn_number', 0)}"


class HybridRAG(BaseRAG):

    def retrieve(self, query: str, storage: StorageInterface, limit: int = None) -> List[Dict[str, Any]]:
        try:
            recent = storage.get_recent(self.config.rag_recent_limit)
            try:
                relevant = storage.search(query, self.config.rag_semantic_limit + len(recent))
            except Exception:
                relevant = []
            seen = {_key(t) for t in recent}
            memories = []
            for t in relevant:
                if _key(t) not in seen:
                    seen.add(_key(t))
                    memories.append(dict(t, _memory=True))
                if len(memories) >= self.config.rag_semantic_limit:
                    break
            # older memories first, then the live conversation in order
            memories.sort(key=lambda x: x.get('timestamp', 0))
            return memories + recent
        except Exception as e:
            raise RAGError(f"Hybrid RAG failed: {e}")
