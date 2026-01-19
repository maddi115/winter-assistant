"""AI inference engine - LFM2.5 GPU swap"""
from typing import List, Dict, Any, Iterator
from core.errors import AIError
from core.llm_lfm import LFM2_5AI

class OllamaAI:
    """LFM2.5-based AI implementation compatible with Winter"""

    def __init__(self, config):
        self.model = LFM2_5AI()

    def generate(self, user_input: str, context: List[Dict[str, Any]]) -> Iterator[str]:
        """Generate streaming response with context"""
        try:
            history_str = ""
            if context:
                for turn in context[-5:]:
                    history_str += f"\nUser: {turn['user']}\nagentWinter: {turn['assistant']}\n"

            # Improved system prompt - makes AI self-aware about its architecture
            prompt = f"""You are agentWinter, a RAG-based AI assistant with LanceDB vector memory.

CRITICAL CONTEXT ABOUT YOUR SYSTEM:
- You are running on LFM2.5-1.2B (Liquid AI) with GPU acceleration
- Your memory uses hybrid RAG: LanceDB vector embeddings + semantic search
- You can only access the CURRENT conversation's history unless the user loads a past one
- When users ask about "your memory" or "improving memory", they mean the technical RAG/storage system
- You are a software system, not a human - respond about YOUR architecture when asked

Conversation History:{history_str}

Current question: {user_input}
agentWinter:"""

            output = self.model.generate(prompt)
            for line in output.split("\n"):
                yield line

        except Exception as e:
            raise AIError(f"AI generation failed: {e}")
