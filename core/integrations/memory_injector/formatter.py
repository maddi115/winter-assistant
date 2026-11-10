"""Formatter - turns a stored fact into a first-person reply (the agent speaks as the owner)."""


class Formatter:
    def __init__(self, persona_name: str = "Maddi"):
        self.persona = persona_name

    def format_response(self, key: str, fact_data: dict) -> str:
        value = fact_data['value']
        templates = {
            'USER_NAME': f"I'm {value}.",
            'PROJECT': f"I'm working on {value}.",
            'GPU': f"I've got an {value}.",
            'LOCATION': f"I'm in {value}.",
            'AI_DISCLOSURE': (f"Yeah, I'm {value}, an AI that talks as {self.persona} "
                              f"using things {self.persona} actually said."),
            'AI_NAME': f"I'm {value}.",
            'AI_MODEL': f"I'm running {value}.",
            'AI_STORAGE': f"I use {value}.",
            'AI_EMBEDDING': f"I use {value} for embeddings.",
        }
        text = templates.get(key, value)
        source = "memory.txt" if fact_data['type'] == 'vessel' else "system.txt"
        return f"{text}\n   [{source} · {fact_data['type']} {fact_data['number']}]"
