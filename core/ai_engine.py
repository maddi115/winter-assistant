"""General chat (small talk, ideas, how-to) - the only place the AI writes freely.

Speaks AS the owner in first person, with real chat roles, streaming,
memory.txt facts in the prompt and a few real messages as style samples.
"""
from typing import List, Dict, Any, Iterator

from core.errors import AIError
from core.llm_ollama import OllamaLLM
from core.integrations.memory_injector import Vessels


def persona_prompt(config, facts_text: str, style: List[str] = None) -> str:
    """Style is described in WORDS, not with sample messages:
    small models copy sample lines word for word."""
    p, label = config.persona_name, config.agent_label
    return (
        f"You are {label}, {p}'s AI. You talk AS {p}, in first person (I/me/my), like a real person texting.\n"
        f"Style: {config.style_words}.\n"
        f"Keep replies short (1-3 sentences) unless asked for more. Stay on what the person just said.\n"
        f"Facts about {p} you can use:\n{facts_text or '(none)'}\n"
        f"Rules:\n"
        f"- You ARE {p}. Never say 'my owner', never talk about {p} in third person, never use he/she/her/him for {p}.\n"
        f"- Only mention the facts above if the person asks about them directly.\n"
        f"- Never invent personal facts, memories, likes or opinions for {p}. "
        f"If asked about something personal you don't know, say you've never really talked about it.\n"
        f"- If someone is rude, stay chill and short, don't lecture.\n"
        f"- If someone asks whether you're an AI, say yes: you're {label}, {p}'s AI.\n"
        f"- General knowledge and casual chat are fine."
    )


class OllamaAI:
    def __init__(self, config, style_samples=None):
        self.config = config
        self.model = OllamaLLM(config.model_name, num_ctx=config.num_ctx, think=config.think,
                               temperature=config.temperature, timeout=config.llm_timeout)
        self.vessels = Vessels()
        self.style = style_samples or []

    def no_evidence_reply(self, question: str) -> str:
        """Last step, only when my own messages don't answer a question about me.
        The AI may react, say I've never talked about it, or answer the general part,
        but must NOT invent a like, dislike, memory or fact about me (checked after)."""
        p = self.config.persona_name
        # no style samples here: small models copy them word for word
        system = (
            f"You are {self.config.agent_label}, talking AS {p} in first person, casual, lowercase is fine.\n"
            f"{p}'s saved messages say NOTHING about this question.\n"
            f"Rules:\n"
            f"- Start by saying you've never really talked about it (or idk / not sure).\n"
            f"- Do NOT claim any like, dislike, favorite, opinion, memory, place, or fact about {p}.\n"
            f"- You may ask something back. Max 2 short sentences.\n"
            f"Examples:\n"
            f"Q: do you like quantum physics?\nA: honestly I've never really talked about quantum physics. why, are you into it?\n"
            f"Q: have you been to japan?\nA: never really talked about that tbh. have you been?\n"
            f"Q: whats your favorite movie?\nA: idk, I've never really said. what's yours?"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
        return "".join(self.model.stream(messages, max_tokens=80)).strip()

    FACT_TOPICS = {
        'USER_NAME': r"\bname\b|\bwho\b",
        'LOCATION': r"\bwhere\b|\blive\b|\bfrom\b|\bcity\b|\blocation\b|\bbased\b",
        'GPU': r"\bgpu\b|\bgraphics\b|\bvram\b|\bpc\b|\bcomputer\b|\bspecs\b",
        'PROJECT': r"\bproject\b|\bworking on\b|\bbuilding\b|\bmaking\b",
    }

    def relevant_facts(self, user_input: str) -> str:
        """Only give the AI the facts the message is about (so it can't blurt out your city)."""
        import re
        low = user_input.lower()
        lines = [f"{k} = {d['value']}" for k, d in self.vessels.vessels.items()
                 if k in self.FACT_TOPICS and re.search(self.FACT_TOPICS[k], low)]
        return "\n".join(lines)

    def generate(self, user_input: str, context: List[Dict[str, Any]]) -> Iterator[str]:
        """Stream a reply as text pieces (newlines kept)."""
        try:
            messages = [{"role": "system",
                         "content": persona_prompt(self.config, self.relevant_facts(user_input), self.style)}]
            for turn in context:
                if turn.get('user'):
                    messages.append({"role": "user", "content": turn['user']})
                if turn.get('assistant'):
                    messages.append({"role": "assistant", "content": turn['assistant']})
            messages.append({"role": "user", "content": user_input})
            yield from self.model.stream(messages, max_tokens=self.config.max_reply_tokens)
        except Exception as e:
            raise AIError(f"AI generation failed: {e}")
