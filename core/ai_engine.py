"""AI inference engine - isolated from storage/UI"""
import subprocess
from typing import List, Dict, Any, Iterator
from core.interfaces import AIInterface
from core.errors import AIError

class OllamaAI(AIInterface):
    """Ollama-based AI implementation"""
    
    def __init__(self, config):
        self.model = config.ai_model
    
    def generate(self, user_input: str, context: List[Dict[str, Any]]) -> Iterator[str]:
        """Generate streaming response with context"""
        
        # Build conversation history from context
        history_str = ""
        if context:
            for turn in context[-5:]:  # Last 5 for token efficiency
                history_str += f"\nUser: {turn['user']}\nagentWinter: {turn['assistant']}\n"
        
        # IMPROVED PROMPT: Make AI actually use conversation history
        prompt = f"""You are agentWinter, a helpful AI assistant with conversation memory.

CRITICAL INSTRUCTIONS:
1. READ the conversation history carefully before responding
2. When asked about past information, answer based on what was PREVIOUSLY discussed
3. When users share information about themselves, it's THEIR information (not yours)
4. Use conversation history to maintain context and continuity

Examples:
- User says "my name is John" → You respond: "Nice to meet you, John!"
- User asks "what's my name?" → Check history, respond: "Your name is John"
- User says "I like pizza" → You respond: "Good to know you like pizza!"
- User asks "what do I like?" → Check history, respond: "You mentioned you like pizza"

Conversation History:{history_str}

Current question: {user_input}
agentWinter:"""
        
        try:
            process = subprocess.Popen(
                ['ollama', 'run', self.model, prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
            
            in_thinking = False
            for line in process.stdout:
                if "Thinking..." in line:
                    in_thinking = True
                    continue
                if "...done thinking." in line:
                    in_thinking = False
                    continue
                if not in_thinking:
                    yield line
                    
        except Exception as e:
            raise AIError(f"AI generation failed: {e}")
