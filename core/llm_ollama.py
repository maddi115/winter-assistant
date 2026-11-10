"""Ollama client: real chat roles, streaming, forced-JSON replies, thinking off."""
import ollama


class OllamaLLM:
    def __init__(self, model_name="qwen3.5:4b", num_ctx=8192, think=False, temperature=0.7):
        print(f"🤖 Connecting to Ollama with {model_name}...")
        self.model_name = model_name
        self.num_ctx = num_ctx
        self.think = think
        self.temperature = temperature
        try:
            ollama.list()
            print(f"✅ Ollama connected - using {model_name}")
        except Exception as e:
            print(f"❌ Ollama connection failed: {e}")
            print("💡 Make sure Ollama is running: 'ollama serve'")
            raise

    def _call(self, **kw):
        kw.setdefault("model", self.model_name)
        try:
            return ollama.chat(think=self.think, **kw)
        except TypeError:
            # older ollama-python without the `think` argument
            return ollama.chat(**kw)

    def _options(self, temperature=None, max_tokens=512):
        return {
            "temperature": self.temperature if temperature is None else temperature,
            "num_predict": max_tokens,
            "num_ctx": self.num_ctx,
        }

    def stream(self, messages, max_tokens=512, temperature=None):
        """Yield text pieces as they are generated (keeps newlines)."""
        for part in self._call(messages=messages, stream=True,
                               options=self._options(temperature, max_tokens)):
            piece = part["message"]["content"]
            if piece:
                yield piece

    def chat_json(self, messages, schema, max_tokens=120, temperature=0.0):
        """One reply forced to match a JSON schema. Returns the raw string."""
        r = self._call(messages=messages, stream=False, format=schema,
                       options=self._options(temperature, max_tokens))
        return r["message"]["content"]

    def generate(self, prompt, max_tokens=512):
        """Old single-prompt API, kept for compatibility."""
        return "".join(self.stream([{"role": "user", "content": prompt}], max_tokens))
