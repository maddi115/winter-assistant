#!/usr/bin/env python
"""
Winter Assistant - agentWinter (Maddi's AI)
Answers questions about Maddi from Maddi's own words (Evidence-Transport-Model),
and chats normally about everything else.
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


def build_transport(config, storage, llm):
    """Evidence store + two searches + transport model. Returns (transport, style_samples)."""
    try:
        from core.embedder import get_embedder
        from storage.evidence_store import EvidenceStore
        from retrieval.evidence_search import EvidenceSearch
        from transport import TransportModel

        store = EvidenceStore(config, db=getattr(storage, "db", None))
        if not store.ready:
            print("ℹ️  No evidence imported yet - questions about you will use normal chat.")
            print("   Import with: python tools/import_chats.py <your_chats.csv> --source twitch\n")
            return None, []
        searcher = EvidenceSearch(store, get_embedder(config), k=config.evidence_k)
        style = store.style_samples(config.style_samples)
        print(f"✅ Evidence ready: {len(store.rows)} of your messages "
              f"(mode={config.transport_mode}, votes={config.votes})\n")
        return TransportModel(config, searcher, llm=llm, style_samples=style), style
    except Exception as e:
        print(f"⚠️  Transport model disabled: {e}\n")
        return None, []


def main():
    config = Config.load()
    print(f"🚀 Winter Assistant - {config.agent_label}\n")

    print("📦 Initializing storage...")
    try:
        storage = LanceDBStorage(config)
        print("✅ LanceDB storage ready\n")
    except StorageError as e:
        print(f"⚠️  LanceDB failed: {e}")
        print("📦 Falling back to JSONL storage\n")
        storage = JSONLStorage(config)

    print("🔍 Loading conversations...\n")
    choice = show_conversation_selector(storage)
    if choice is None:
        print("\n👋 Goodbye!\n")
        sys.exit(0)

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

    print("🔍 Initializing RAG...")
    try:
        rag = HybridRAG(config)
        print("✅ Hybrid RAG (recent + semantic, all chats) ready\n")
    except Exception as e:
        print(f"⚠️  Hybrid RAG failed: {e}\n🔍 Falling back to simple RAG\n")
        rag = SimpleRAG(config)

    print("🤖 Initializing AI...")
    try:
        ai = OllamaAI(config)
        print("✅ AI engine ready\n")
    except Exception as e:
        print(f"❌ AI initialization failed: {e}")
        sys.exit(1)

    transport, style = build_transport(config, storage, ai.model)
    ai.style = style

    adapter = ConversationAdapter(storage, rag, ai, transport=transport, config=config)
    ui = TerminalUI(adapter, conversation_title or "", label=config.agent_label, debug=config.debug,
                    persona=config.persona_name)
    try:
        ui.run()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
