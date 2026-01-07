"""Conversation selection menu - startup UI component"""
from typing import Optional
from core.interfaces import StorageInterface
from ui.conversation_list import show_conversation_list

def show_conversation_selector(storage: StorageInterface) -> Optional[str]:
    """
    Show conversation selection menu
    
    Returns:
        None: User quit
        "new": Start new conversation
        str: conversation_id to load
    """
    
    # Get all conversations (already sorted newest first by storage)
    try:
        conversations = storage.list_all_conversations()
    except Exception as e:
        print(f"⚠️  Error loading conversations: {e}")
        conversations = []
    
    # Show paginated list
    return show_conversation_list(conversations)
