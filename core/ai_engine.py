"""AI inference engine - LFM2.5 GPU swap"""
from typing import List, Dict, Any, Iterator
from pathlib import Path
from core.errors import AIError
from core.llm_lfm import LFM2_5AI

class OllamaAI:
    """LFM2.5-based AI implementation compatible with Winter"""

    def __init__(self, config):
        self.model = LFM2_5AI()
        self.vessels_text = self._load_vessels()
    
    def _load_vessels(self) -> str:
        """Load user vessels for injection into complex prompts"""
        vessels_file = Path("memory/memory.txt")
        if not vessels_file.exists():
            return ""
        
        lines = ["[USER FACTS - Reference these when relevant:]"]
        for line in vessels_file.read_text().splitlines():
            if line.strip():
                lines.append(line.strip())
        lines.append("[END USER FACTS]")
        return "\n".join(lines)

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
- Your memory: LanceDB with vector embeddings (sentence-transformers/all-MiniLM-L6-v2)
- Your storage: Hybrid RAG (recent context + semantic search)

{self.vessels_text}

CONTEXT ABOUT YOUR SYSTEM:
- You can only access the CURRENT conversation's history unless the user loads a past one
- When users ask about "your memory", they mean the technical RAG/storage system
- You are a software system, not a human

Conversation History:{history_str}

Current question: {user_input}
agentWinter:"""

            output = self.model.generate(prompt)
            for line in output.split("\n"):
                yield line

        except Exception as e:
            raise AIError(f"AI generation failed: {e}")
