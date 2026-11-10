"""General chat (small talk, ideas, how-to) - the only place the AI writes freely.

Speaks AS the owner in first person, with real chat roles, streaming,
memory.txt facts in the prompt and a few real messages as style samples.
"""
from typing import List, Dict, Any, Iterator

from core.errors import AIError
from core.llm_ollama import OllamaLLM
from core.integrations.memory_injector import Vessels


def persona_prompt(config, facts_text: str, style: List[str]) -> str:
    p, label = config.persona_name, config.agent_label
    style_block = "\n".join(f"- {s}" for s in style) if style else "- (no samples yet)"
    return (
        f"You are {label}. You talk AS {p}, in first person (I/me/my), casually, like a real person texting.\n"
        f"Keep replies short (1-3 sentences) unless asked for more.\n"
        f"Facts about {p} you can use:\n{facts_text or '(none)'}\n"
        f"How {p} types (copy the vibe, not the content):\n{style_block}\n"
        f"Rules:\n"
        f"- Never invent personal facts, memories, likes or opinions for {p}. "
        f"If asked about something personal you don't know, say you've never really talked about it.\n"
        f"- If someone asks whether you're an AI, say yes: you're {label}.\n"
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
        system = persona_prompt(self.config, self.vessels.get_all_text(), self.style) + (
            f"\n\nIMPORTANT: {p}'s saved messages say NOTHING about this question.\n"
            f"- Do NOT claim any like, dislike, favorite, opinion, memory or fact about {p}.\n"
            f"- You MAY say you've never really talked about it, react casually, ask something back, "
            f"or answer the general-knowledge part.\n"
            f"- Max 2 short sentences."
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
        return "".join(self.model.stream(messages, max_tokens=80)).strip()

    def generate(self, user_input: str, context: List[Dict[str, Any]]) -> Iterator[str]:
        """Stream a reply as text pieces (newlines kept)."""
        try:
            messages = [{"role": "system",
                         "content": persona_prompt(self.config, self.vessels.get_all_text(), self.style)}]
            for turn in context:
                if turn.get('user'):
                    messages.append({"role": "user", "content": turn['user']})
                if turn.get('assistant'):
                    messages.append({"role": "assistant", "content": turn['assistant']})
            messages.append({"role": "user", "content": user_input})
            yield from self.model.stream(messages, max_tokens=self.config.max_reply_tokens)
        except Exception as e:
            raise AIError(f"AI generation failed: {e}")
