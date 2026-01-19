#!/usr/bin/env python
"""
Winter Assistant - Modular AI Chat System
Use first user message as conversation title for new conversations
"""
import sys

from core.config import Config
from core.ai_engine import OllamaAI
from storage.lancedb_storage import LanceDBStorage
from storage.fallback_storage import JSONLStorage
from retrieval.hybrid_rag import HybridRAG
from retrieval.simple_rag import SimpleRAG
from adapters.conversation_adapter import ConversationAdapter
from ui.terminal import TerminalUI
from ui.selection_menu import show_conversation_selector
from core.errors import StorageError

def main():
    """Main entry point with conversation selector"""

    print("🚀 Winter Assistant - Modular Edition\n")

    # Load configuration
    config = Config.load()

    # Initialize storage (with fallback)
    print("📦 Initializing storage...")
    try:
        storage = LanceDBStorage(config)
        print("✅ LanceDB storage ready\n")
    except StorageError as e:
        print(f"⚠️  LanceDB failed: {e}")
        print("📦 Falling back to JSONL storage\n")
        storage = JSONLStorage(config)

    # Show conversation selector
    print("🔍 Loading conversations...\n")
    choice = show_conversation_selector(storage)

    if choice is None:
        print("\n👋 Goodbye!\n")
        sys.exit(0)

    # Load conversation or start new
    conversation_title = None
    if choice != "new":
        try:
            storage.load_conversation(choice)
            turns = storage.get_all_turns()
            conversation_title = turns[0].get('user', 'Conversation') if turns else "Conversation"
            print(f"\n📜 Loaded: {conversation_title}\n")
        except Exception as e:
            print(f"\n⚠️  Failed to load conversation: {e}")
            conversation_title = "Conversation"

    # Initialize RAG (with fallback)
    print("🔍 Initializing RAG...")
    try:
        rag = HybridRAG(config)
        print("✅ Hybrid RAG (recency + semantic) ready\n")
    except Exception as e:
        print(f"⚠️  Hybrid RAG failed: {e}")
        print("🔍 Falling back to simple RAG\n")
        rag = SimpleRAG(config)

    # Initialize AI
    print("🤖 Initializing AI...")
    try:
        ai = OllamaAI(config)
        print("✅ AI engine ready\n")
    except Exception as e:
        print(f"❌ AI initialization failed: {e}")
        sys.exit(1)

    # Wire everything together
    adapter = ConversationAdapter(storage, rag, ai)

    # Initialize UI with optional placeholder; title will update on first user input
    ui = TerminalUI(adapter, conversation_title or "")

    # Run
    try:
        ui.run()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
