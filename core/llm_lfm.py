import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "LiquidAI/LFM2.5-1.2B-Instruct"

class LFM2_5AI:
    def __init__(self):
        print("🤖 Loading LFM2.5-1.2B on GPU...")
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="auto"
        ).eval()
        print("✅ LFM2.5 loaded successfully.")

    def generate(self, prompt, max_tokens=512):
        inputs = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(self.model.device)

        output = self.model.generate(
            inputs,
            do_sample=True,           # ← ADD THIS to enable temperature/top_p
            temperature=0.1,
            top_k=50,
            top_p=0.1,
            repetition_penalty=1.05,
            max_new_tokens=max_tokens
        )

        return self.tokenizer.decode(output[0][inputs.shape[-1]:], skip_special_tokens=True)
