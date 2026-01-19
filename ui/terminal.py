"""Terminal UI implementation"""
import sys
from typing import Optional

from ui.components import get_key, menu, clear_screen
from adapters.conversation_adapter import ConversationAdapter
from core.errors import UIError

class TerminalUI:
    """Terminal-based user interface"""

    def __init__(self, adapter: ConversationAdapter, conversation_title: str = ""):
        self.adapter = adapter
        self.conversation_title = conversation_title
        self.first_input_received = False

    def run(self):
        """Main UI loop"""
        clear_screen()
        self.show_header()

        while True:
            try:
                user_input = input("💬 You: ").strip()

                if not user_input or user_input.lower() in ['quit', 'exit', 'q']:
                    print("\n👋 Goodbye!\n")
                    break

                # Set first user input as conversation title if empty
                if not self.first_input_received:
                    if not self.conversation_title:
                        self.conversation_title = user_input
                    self.first_input_received = True
                    # Refresh header to show new title
                    clear_screen()
                    self.show_header()

                # Handle commands
                if user_input.lower() == 'history':
                    self.show_history()
                    continue

                if user_input.lower().startswith('search '):
                    query = user_input[7:].strip()
                    self.show_search_results(query)
                    continue

                # Chat
                print("\n🤖 ", end='', flush=True)
                for chunk in self.adapter.chat(user_input):
                    print(chunk, end='', flush=True)
                print()

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!\n")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")

    def show_header(self):
        """Display header"""
        print("="*60)
        title_display = self.conversation_title if self.conversation_title else "WINTER ASSISTANT"
        print(f"🚀 WINTER ASSISTANT - {title_display}")
        print("="*60)
        print("\nCommands: history | search <query> | quit\n")

    def show_history(self):
        """Display recent conversation history"""
        turns = self.adapter.get_recent_turns(10)

        if not turns:
            print("\n📜 No conversation history yet\n")
            return

        print("\n📜 RECENT CONVERSATION\n")
        for t in turns:
            print(f"[{t.get('datetime', 'N/A')}]")
            print(f"You: {t.get('user', '')[:70]}")
            print(f"AI: {t.get('assistant', '')[:100]}")
            print()

    def show_search_results(self, query: str):
        """Display search results"""
        print(f"\n🔍 Searching for: {query}\n")

        results = self.adapter.search_history(query, limit=5)

        if not results:
            print("No results found.\n")
            return

        for i, r in enumerate(results, 1):
            print(f"📍 Result {i} - Turn {r.get('turn_number', 0)}")
            print(f"   [{r.get('datetime', 'N/A')}]")
            print(f"   You: {r.get('user', '')[:60]}...")
            print(f"   AI: {r.get('assistant', '')[:80]}...")
            print()
