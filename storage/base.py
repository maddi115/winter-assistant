"""Base storage implementation"""
from abc import abstractmethod
from typing import List, Dict, Any
from core.interfaces import StorageInterface

class BaseStorage(StorageInterface):
    """Base class with common storage logic"""
    
    def __init__(self, config):
        self.config = config
        self.project = "conversations"
        self.conversation_id = None
    
    def set_project(self, project: str):
        """Set current project"""
        self.project = project
    
    def set_conversation(self, conversation_id: str):
        """Set current conversation"""
        self.conversation_id = conversation_id
    
    @abstractmethod
    def list_all_conversations(self) -> List[Dict[str, Any]]:
        """List all conversations with metadata"""
        pass
    
    @abstractmethod
    def load_conversation(self, conversation_id: str) -> None:
        """Load existing conversation by ID"""
        pass
