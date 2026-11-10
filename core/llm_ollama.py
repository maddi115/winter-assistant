"""Ollama client: real chat roles, streaming, forced-JSON replies, thinking off."""
import ollama


class OllamaLLM:
    def __init__(self, model_name="qwen3.5:4b", num_ctx=4096, think=False, temperature=0.7,
                 timeout=90, warm_up=True):
        print(f"🤖 Connecting to Ollama with {model_name}...")
        self.model_name = model_name
        self.num_ctx = num_ctx          # keep ONE value: changing it makes Ollama reload the model
        self.think = think
        self.temperature = temperature
        self.client = ollama.Client(timeout=timeout)   # never wait forever
        try:
            self.client.list()
            print(f"✅ Ollama connected - using {model_name}")
        except Exception as e:
            print(f"❌ Ollama connection failed: {e}")
            print("💡 Make sure Ollama is running: 'ollama serve'")
            raise
        if warm_up:
            self.warm_up()

    def warm_up(self):
        """Load the model into the GPU now, so the first question isn't slow."""
        import time
        t = time.time()
        print("🔥 Loading model into the GPU (first time can take ~30s)...", flush=True)
        try:
            self.client.generate(model=self.model_name, prompt="", keep_alive="30m",
                                 options={"num_ctx": self.num_ctx})
            print(f"✅ Model loaded in {time.time() - t:.1f}s")
        except Exception as e:
            print(f"⚠️  Warm-up failed ({e}) - will try again on the first question")

    def _call(self, **kw):
        kw.setdefault("model", self.model_name)
        kw.setdefault("keep_alive", "30m")
        try:
            return self.client.chat(think=self.think, **kw)
        except TypeError:
            # older ollama-python without the `think` argument
            return self.client.chat(**kw)

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
