"""Formatter - Rich highlighting for vessel responses"""

class Formatter:
    """Format vessel responses with Rich markup"""
    
    @staticmethod
    def format_response(key: str, fact_data: dict) -> str:
        """Format fact response with Rich markup"""
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
            attribution = f"[bold magenta on black][FROM: memory.txt vessel {number}: {key}][/]"
            return f"{response} {attribution}"
        else:
            return response
