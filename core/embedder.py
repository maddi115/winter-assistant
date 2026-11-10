"""Shared embedding model - loaded ONCE and reused by every module.

Offline by default (the model must already be downloaded).
First run on a new PC:  WINTER_ALLOW_DOWNLOAD=1 python main.py
"""
import os

if os.environ.get("WINTER_ALLOW_DOWNLOAD") != "1":
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

from typing import List
import numpy as np

_CACHE = {}


class Embedder:
    """Wraps sentence-transformers. All vectors come back L2-normalized."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        offline = os.environ.get("WINTER_ALLOW_DOWNLOAD") != "1"
        kw = {}
        try:
            import torch
            if torch.cuda.is_available():
                kw["model_kwargs"] = {"torch_dtype": torch.float16}   # half the VRAM
        except Exception:
            pass
        self.model = SentenceTransformer(model_name, local_files_only=offline, **kw)
        self.dim = self.model.get_sentence_embedding_dimension()

    @staticmethod
    def _norm(v: np.ndarray) -> np.ndarray:
        v = np.asarray(v, dtype=np.float32)
        n = np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9
        return v / n

    def encode_docs(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        return self._norm(self.model.encode(texts, batch_size=batch_size,
                                            show_progress_bar=len(texts) > 500))

    def encode_query(self, text: str) -> np.ndarray:
        # Qwen3-Embedding works best with its "query" prompt; other models ignore it
        try:
            v = self.model.encode([text], prompt_name="query")
        except Exception:
            v = self.model.encode([text])
        return self._norm(v)[0]


def get_embedder(config) -> Embedder:
    name = config.embedding_model
    if name not in _CACHE:
        print(f"🔄 Loading embedding model {name}...")
        _CACHE[name] = Embedder(name)
    return _CACHE[name]
