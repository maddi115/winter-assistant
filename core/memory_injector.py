"""Memory injection and routing system"""
import re
from pathlib import Path
from typing import Optional, Dict, Tuple
from colorama import Fore, Back, Style

class MemoryInjector:
    """Routes questions to direct facts or AI reasoning"""
    
    def __init__(self):
        self.vessels = self._load_file("memory/memory.txt", "vessel")
        self.system_facts = self._load_file("memory/system.txt", "system")
        self.patterns = self._build_patterns()
    
    def _load_file(self, filepath: str, prefix: str) -> Dict:
        """Parse memory file into dictionary"""
        path = Path(filepath)
        if not path.exists():
            return {}
        
        facts = {}
        for line in path.read_text().splitlines():
            match = re.match(rf'{prefix} (\d+): (\w+) = (.+)', line.strip())
            if match:
                num, key, value = match.groups()
                facts[key] = {
                    'value': value.strip(),
                    'number': num,
                    'type': prefix
                }
        return facts
    
    def _build_patterns(self) -> Dict:
        """Define patterns for routing questions to facts"""
        return {
            'USER_NAME': [r'\bmy name\b', r'what.*i called', r'who am i', r"what's my name", r'name again'],
            'PROJECT': [r'\bmy project\b', r'working on', r'building', r"what's.*project"],
            'GPU': [r'\bmy gpu\b', r'what.*graphics', r'gpu.*have', r'what gpu'],
            'LOCATION': [r'where am i', r'my location', r'what.*city'],  # More specific!
            'AI_NAME': [r'\byour name\b', r'who are you', r"what's your name"],
            'AI_MODEL': [r'\bwhat model\b', r'which.*llm', r'what.*model.*you'],
            'AI_PURPOSE': [r'what.*you do', r'your purpose'],
            'AI_STORAGE': [r'how.*store', r'what.*database'],
            'AI_EMBEDDING': [r'embedding model', r'what.*embeddings']
        }
    
    def _is_question(self, text: str) -> bool:
        """Check if input is actually a question"""
        text_lower = text.lower().strip()
        
        # Question markers
        if text.endswith('?'):
            # But exclude rhetorical/statement questions like "you know where i live?"
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
        
        # Question words at start
        question_words = ['what', 'where', 'who', 'when', 'why', 'how', 'which']
        first_word = text_lower.split()[0] if text_lower.split() else ''
        return first_word in question_words
    
    def route(self, user_input: str) -> Tuple[Optional[str], Optional[Dict]]:
        """Route question to fact or AI"""
        # Skip routing if not a real question
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
    
    def format_response(self, key: str, fact_data: Dict) -> str:
        """Format fact response with attribution"""
        value = fact_data['value']
        fact_type = fact_data['type']
        number = fact_data['number']
        
        templates = {
            'USER_NAME': f"Your name is {value}.",
            'PROJECT': f"You're working on {value}.",
            'GPU': f"You have a {value}.",
            'LOCATION': f"You're in {value}.",
            'AI_NAME': f"I'm {value}.",
            'AI_MODEL': f"I'm running {value}.",
            'AI_PURPOSE': f"I'm {value}.",
            'AI_STORAGE': f"I use {value}.",
            'AI_EMBEDDING': f"I use {value} for embeddings."
        }
        
        response = templates.get(key, value)
        
        if fact_type == 'vessel':
            attribution = f"{Back.RED}{Fore.WHITE}[FROM: memory.txt vessel {number}: {key}]{Style.RESET_ALL}"
            return f"{response} {attribution}"
        else:
            return response
    
    def get_all_vessels_text(self) -> str:
        """Get all vessels as text for AI prompt injection"""
        if not self.vessels:
            return ""
        
        lines = ["[USER FACTS - Always cite these exactly:]"]
        for key, data in self.vessels.items():
            lines.append(f"vessel {data['number']}: {key} = {data['value']}")
        lines.append("[END USER FACTS]")
        return "\n".join(lines)
