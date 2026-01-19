"""AI inference engine - LFM2.5 GPU swap"""
from typing import List, Dict, Any, Iterator
from core.errors import AIError
from core.llm_lfm import LFM2_5AI

class OllamaAI:
    """LFM2.5-based AI implementation compatible with Winter"""

    def __init__(self, config):
        # Load LFM2.5 model on GPU
        self.model = LFM2_5AI()

    def generate(self, user_input: str, context: List[Dict[str, Any]]) -> Iterator[str]:
        """Generate streaming response with context"""
        try:
            # Build conversation history string
            history_str = ""
            if context:
                for turn in context[-5:]:
                    history_str += f"\nUser: {turn['user']}\nagentWinter: {turn['assistant']}\n"

            # Combine with current user input
            prompt = f"""You are agentWinter, a helpful AI assistant with conversation memory.

Conversation History:{history_str}

Current question: {user_input}
agentWinter:"""

            # LFM2.5 returns full response; we yield line by line for streaming
            output = self.model.generate(prompt)
            for line in output.split("\n"):
                yield line

        except Exception as e:
            raise AIError(f"AI generation failed: {e}")
