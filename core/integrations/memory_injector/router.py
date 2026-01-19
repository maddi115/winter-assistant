"""Router - pattern matching and question routing"""
import re
from typing import Optional, Dict, Tuple

class Router:
    """Routes questions to direct facts or AI reasoning"""
    
    def __init__(self, vessels_obj):
        self.vessels = vessels_obj.vessels
        self.system_facts = vessels_obj.system_facts
        self.patterns = self._build_patterns()
    
    def _build_patterns(self) -> Dict:
        """Define patterns for routing questions to facts"""
        return {
            'USER_NAME': [r'\bmy name\b', r'what.*i called', r'who am i', r"what's my name", r'name again'],
            'PROJECT': [r'\bmy project\b', r'working on', r'building', r"what's.*project"],
            'GPU': [r'\bmy gpu\b', r'what.*graphics', r'gpu.*have', r'what gpu', r'\bvram\b', r'how much vram', r'video memory'],
            'LOCATION': [r'where am i', r'my location', r'what.*city', r"what's my location", r'whats my location'],
            'AI_NAME': [r'\byour name\b', r'who are you', r"what's your name"],
            'AI_MODEL': [r'\bwhat model\b', r'which.*llm', r'what.*model.*you'],
            'AI_PURPOSE': [r'what.*you do', r'your purpose'],
            'AI_STORAGE': [r'how.*store', r'what.*database'],
            'AI_EMBEDDING': [r'embedding model', r'what.*embeddings']
        }
    
    def _is_question(self, text: str) -> bool:
        """Check if input is actually a question"""
        text_lower = text.lower().strip()
        
        if text.endswith('?'):
            negative_patterns = [
                r'you know',
                r'you have',
                r'thats? creepy',
                r'creeper',
                r'why do you',
                r'how do you know'
            ]
            for pattern in negative_patterns:
                if re.search(pattern, text_lower):
                    return False
            return True
        
        question_words = ['what', 'where', 'who', 'when', 'why', 'how', 'which']
        first_word = text_lower.split()[0] if text_lower.split() else ''
        return first_word in question_words
    
    def route(self, user_input: str) -> Tuple[Optional[str], Optional[Dict]]:
        """Route question to fact or AI"""
        if not self._is_question(user_input):
            return None, None
        
        user_lower = user_input.lower()
        
        for key, patterns in self.patterns.items():
            if key in self.vessels:
                for pattern in patterns:
                    if re.search(pattern, user_lower):
                        return key, self.vessels[key]
        
        for key, patterns in self.patterns.items():
            if key in self.system_facts:
                for pattern in patterns:
                    if re.search(pattern, user_lower):
                        return key, self.system_facts[key]
        
        return None, None
