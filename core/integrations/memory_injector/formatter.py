"""Formatter - turns a stored fact (vessel) into a reply.

"what's MY name?"  (owner asking)  -> "Your name is Maddi."
"where are YOU from?" (about the agent, who talks as the owner) -> "I'm in Los Angeles."
The part pulled from the vessel is highlighted neon pink in the terminal.
"""
from core import colors


class Formatter:
    def __init__(self, persona_name: str = "Maddi"):
        self.persona = persona_name

    def _templates(self, v, owner: bool):
        p = self.persona
        if owner:
            return {
                'USER_NAME': ("Your name is ", v, "."),
                'PROJECT': ("You're working on ", v, "."),
                'GPU': ("You have an ", v, "."),
                'LOCATION': ("You're in ", v, "."),
            }
        return {
            'USER_NAME': (f"I talk as ", v, "."),
            'PROJECT': ("I'm working on ", v, "."),
            'GPU': ("I've got an ", v, "."),
            'LOCATION': ("I'm in ", v, "."),
            'AI_NAME': ("I'm ", v, f", {p}'s AI."),
            'AI_DISCLOSURE': ("Yeah, I'm ", v, f", {p}'s AI. I talk as {p} using things {p} actually said."),
            'AI_OWNER': (f"{p} made me. I'm ", v, f", and I talk as {p} using things {p} actually said."),
            'AI_MODEL': ("I'm running ", v, "."),
            'AI_STORAGE': ("I use ", v, "."),
            'AI_EMBEDDING': ("I use ", v, " for embeddings."),
        }

    def _parts(self, key, fact_data):
        owner = fact_data.get('perspective') == 'owner'
        before, value, after = self._templates(fact_data['value'], owner).get(key, ("", fact_data['value'], ""))
        source = "memory.txt" if fact_data['type'] == 'vessel' else "system.txt"
        cite = f"   [{source} · {fact_data['type']} {fact_data['number']}]"
        return before, value, after, cite

    def format_response(self, key: str, fact_data: dict) -> str:
        """Plain text (saved to history)."""
        b, v, a, cite = self._parts(key, fact_data)
        return f"{b}{v}{a}\n{cite}"

    def format_display(self, key: str, fact_data: dict) -> str:
        """Terminal text: the vessel value in neon pink."""
        b, v, a, cite = self._parts(key, fact_data)
        return f"{b}{colors.pink(v)}{a}\n{colors.dim(cite)}"
