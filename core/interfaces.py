from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class StorageInterface(ABC):
    """Abstract storage interface - swap implementations freely"""
    
    @abstractmethod
    def save_turn(self, user_msg: str, ai_msg: str, metadata: Dict[str, Any]) -> None:
        """Save a conversation turn"""
        pass
    
    @abstractmethod
    def get_recent(self, limit: int) -> List[Dict[str, Any]]:
        """Get recent conversation turns"""
        pass
    
    @abstractmethod
    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search conversations by query"""
        pass
    
    @abstractmethod
    def get_all_turns(self) -> List[Dict[str, Any]]:
        """Get all turns from current conversation"""
        pass
    
    @abstractmethod
    def list_all_conversations(self) -> List[Dict[str, Any]]:
        """List all conversations with metadata"""
        pass
    
    @abstractmethod
    def load_conversation(self, conversation_id: str) -> None:
        """Load existing conversation by ID"""
        pass

class RAGInterface(ABC):
    """Abstract RAG retrieval interface"""
    
    @abstractmethod
    def retrieve(self, query: str, storage: StorageInterface, limit: int) -> List[Dict[str, Any]]:
        """Retrieve relevant context for query"""
        pass

class AIInterface(ABC):
    """Abstract AI inference interface"""
    
    @abstractmethod
    def generate(self, user_input: str, context: List[Dict[str, Any]]) -> str:
        """Generate AI response given context"""
        pass
