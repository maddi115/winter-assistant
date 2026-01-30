import ollama

class OllamaLLM:
    def __init__(self, model_name="deepseek-r1:8b"):
        print(f"🤖 Connecting to Ollama with {model_name}...")
        self.model_name = model_name
        # Test connection
        try:
            ollama.list()
            print(f"✅ Ollama connected - using {model_name}")
        except Exception as e:
            print(f"❌ Ollama connection failed: {e}")
            print("💡 Make sure Ollama is running: 'ollama serve'")
            raise

    def generate(self, prompt, max_tokens=512):
        """Generate response using Ollama API"""
        response = ollama.chat(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.7,
                "num_predict": max_tokens,
            }
        )
        return response['message']['content']
