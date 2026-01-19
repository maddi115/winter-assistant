"""AI inference engine - LFM2.5 GPU swap"""
from typing import List, Dict, Any, Iterator
from core.errors import AIError
from core.llm_lfm import LFM2_5AI
from core.integrations.memory_injector import Vessels

class OllamaAI:
    """LFM2.5-based AI implementation compatible with Winter"""

    def __init__(self, config):
        self.model = LFM2_5AI()
        self.vessels = Vessels()

    def generate(self, user_input: str, context: List[Dict[str, Any]]) -> Iterator[str]:
        """Generate streaming response with context"""
        try:
            history_str = ""
            if context:
                for turn in context[-5:]:
                    history_str += f"\nUser: {turn['user']}\nagentWinter: {turn['assistant']}\n"

            # System prompt with vessel injection
            prompt = f"""You are agentWinter, a RAG-based AI assistant.

SYSTEM IDENTITY:
- Your name: agentWinter
- Your model: LFM2.5-1.2B (Liquid AI) with GPU acceleration
- Your memory: LanceDB with vector embeddings (Qwen/Qwen3-Embedding-0.6B)
- Your storage: Hybrid RAG (recent context + semantic search)

{self.vessels.get_all_text()}

Conversation History:{history_str}

Current question: {user_input}
agentWinter:"""

            output = self.model.generate(prompt)
            for line in output.split("\n"):
                yield line

        except Exception as e:
            raise AIError(f"AI generation failed: {e}")
