"""Conversation adapter - decides who answers each message.

  1. Exact fact question       -> memory.txt / system.txt   (no AI)
  2. Question about the owner  -> transport model           (AI only picks numbers)
  3. Everything else           -> general chat              (AI writes)
"""
import time
from typing import Dict, Any, Iterator, Set

from core.interfaces import StorageInterface, RAGInterface
from core.errors import StorageError, RAGError, AIError
from core.integrations.memory_injector import Vessels, Router, Formatter
from transport import classify


class ConversationAdapter:

    def __init__(self, storage: StorageInterface, rag: RAGInterface, ai, transport=None, config=None):
        self.storage = storage
        self.rag = rag
        self.ai = ai
        self.transport = transport
        self.config = config
        self.vessels = Vessels()
        self.router = Router(self.vessels)
        self.formatter = Formatter(config.persona_name if config else "Maddi")
        self.shown: Set[int] = set()          # evidence already shown (no repeats)
        self.last_evidence_q = None
        self.last_route = None
        self.last_debug = {}

    def _save(self, user_input, response, start):
        try:
            self.storage.save_turn(user_input, response, {'elapsed': time.time() - start})
        except StorageError as e:
            print(f"\n⚠️  Storage failed: {e}")

    def _ai_instead_of_idk(self, user_input, res):
        """Everything said my messages don't answer this. Let the AI reply,
        but only keep it if it doesn't invent a like, memory or fact about me."""
        from transport.checker import invents_facts
        try:
            reply = self.ai.no_evidence_reply(user_input)
        except Exception as e:
            res.debug["ai_fallback"] = f"error: {e}"
            return res
        res.debug["ai_fallback"] = reply
        from transport.checker import persona_guard
        reply = persona_guard(reply or "", user_input, self.config.persona_name)
        if not reply or invents_facts(reply) or len(reply.split()) > 45:
            return res                       # unsafe -> plain idk
        res.text, res.display, res.route = reply, "", "ai_no_evidence"
        return res

    def chat(self, user_input: str) -> Iterator[str]:
        start = time.time()

        # 1. exact fact
        fact_key, fact_data = self.router.route(user_input)
        if fact_key and fact_data:
            response = self.formatter.format_response(fact_key, fact_data)
            shown = self.formatter.format_display(fact_key, fact_data)
            self.last_route, self.last_debug = "fact", {}
            self._save(user_input, response, start)
            yield shown
            yield f"\n\n⏱️  {time.time() - start:.2f}s\n"
            return

        # 2. about the owner -> evidence transport
        if self.transport is not None:
            question, exclude = None, set()
            if classify.is_followup(user_input) and self.last_evidence_q:
                question, exclude = self.last_evidence_q, set(self.shown)
            elif classify.is_question(user_input) and classify.about_me(
                    user_input, self.config.persona_name, self.config.owner_handles):
                question = user_input
                self.shown = set()
            if question:
                try:
                    res = self.transport.answer(question, exclude, tone_source=user_input)
                    if (res.route.startswith("idk") and not exclude
                            and getattr(self.config, "idk_mode", "ai") == "ai"
                            and hasattr(self.ai, "no_evidence_reply")):
                        res = self._ai_instead_of_idk(user_input, res)
                    self.shown.update(res.used_ids)
                    self.last_evidence_q = question
                    self.last_route, self.last_debug = res.route, res.debug
                    self._save(user_input, res.text, start)
                    yield res.shown()
                    yield f"\n\n⏱️  {time.time() - start:.2f}s · {res.route}\n"
                    return
                except Exception as e:
                    print(f"⚠️  Transport failed, falling back to chat: {e}")

        # 3. general chat
        try:
            context = self.rag.retrieve(user_input, self.storage)
        except RAGError as e:
            print(f"⚠️  RAG failed, using recent turns: {e}")
            context = self.storage.get_recent(5)
        except Exception as e:
            print(f"⚠️  Retrieval error: {e}")
            context = []

        try:
            chunks = []
            stream = getattr(self.config, "stream_chat", False)
            for chunk in self.ai.generate(user_input, context):
                chunks.append(chunk)
                if stream:
                    yield chunk
            response = ''.join(chunks)
            if not stream:
                from transport.checker import persona_guard
                persona = self.config.persona_name if self.config else "Maddi"
                response = persona_guard(response, user_input, persona)
                yield response
            self.last_route, self.last_debug = "general", {}
            self._save(user_input, response, start)
            yield f"\n\n⏱️  {time.time() - start:.2f}s · general\n"
        except AIError as e:
            yield f"\n❌ AI Error: {e}\n"
        except Exception as e:
            yield f"\n❌ Unexpected error: {e}\n"

    def search_history(self, query: str, limit: int = 5) -> list:
        try:
            return self.storage.search(query, limit)
        except Exception as e:
            print(f"⚠️  Search failed: {e}")
            return []

    def get_recent_turns(self, limit: int = 10) -> list:
        try:
            return self.storage.get_recent(limit)
        except Exception as e:
            print(f"⚠️  History retrieval failed: {e}")
            return []
