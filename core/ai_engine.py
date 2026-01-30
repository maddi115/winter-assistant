"""AI inference engine - LFM2.5 GPU swap"""
from typing import List, Dict, Any, Iterator
from core.errors import AIError
from core.llm_ollama import OllamaLLM
from core.integrations.memory_injector import Vessels, Router, Formatter

class OllamaAI:
    """LFM2.5-based AI implementation compatible with Winter"""
    def __init__(self, config):
        self.model = OllamaLLM(config.model_name)
        self.vessels = Vessels()
        self.router = Router(self.vessels)
        self.formatter = Formatter()
    
    def generate(self, user_input: str, context: List[Dict[str, Any]]) -> Iterator[str]:
        """Generate streaming response with context"""
        try:
            history_str = ""
            if context:
                for turn in context[-15:]:
                    history_str += f"\nUser: {turn['user']}\nAssistant: {turn['assistant']}\n"
            
            # Use Router for selective vessel injection
            fact_key, fact_data = self.router.route(user_input)
            
            if fact_key and fact_data:
                # Direct fact answer - bypass AI
                answer = self.formatter.format_response(fact_key, fact_data)
                yield answer
                return
            
            # Check if user is asking about themselves
            asking_about_self = any(word in user_input.lower() for word in [
                "do i", "did i", "what do i", "what did i", "my favorite", "i like"
            ])
            
            # Build prompt with emphasis on reading conversation history
            if asking_about_self:
                prompt = f"""You are agentWinter, an AI assistant helping Maddi.

CRITICAL: Maddi is asking about THEMSELVES. Look in the conversation history below for what MADDI said, not what you think.

When Maddi asks "what do I like?" or "what did I say?" - find where Maddi (marked as "User:") mentioned it in the conversation below.

CONVERSATION HISTORY:{history_str}

User: {user_input}
Assistant:"""
            else:
                prompt = f"""You are agentWinter, a friendly AI assistant.

Conversation:{history_str}

User: {user_input}
Assistant:"""
            
            output = self.model.generate(prompt)
            for line in output.split("\n"):
                yield line
                
        except Exception as e:
            raise AIError(f"AI generation failed: {e}")
