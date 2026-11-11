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
_THREADS = [2]


def limit_cpu_threads(n):
    """Keep CPU models from each grabbing every core (they fight and pin the CPU at 100%)."""
    n = max(1, int(n or 1))
    _THREADS[0] = n
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[k] = str(n)
    os.environ["MOONSHINE_ORT_SINGLE_THREAD"] = "1"     # moonshine-voice: no spinning thread pool
    try:
        import torch
        torch.set_num_threads(n)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass                                        # already set once - fine
    except Exception:
        pass
    return n


class Embedder:
    """Wraps sentence-transformers. All vectors come back L2-normalized."""

    def __init__(self, model_name: str, device: str = "auto"):
        """device: auto (GPU if there is one) | cpu (frees ~1.2GB of GPU for a bigger chat model) | cuda"""
        from sentence_transformers import SentenceTransformer
        offline = os.environ.get("WINTER_ALLOW_DOWNLOAD") != "1"
        kw = {}
        try:
            import torch
            use_gpu = torch.cuda.is_available() and device != "cpu"
            kw["device"] = "cuda" if use_gpu else "cpu"
            if not use_gpu:
                limit_cpu_threads(_THREADS[0])
            if use_gpu:
                kw["model_kwargs"] = {"dtype": torch.float16}   # half the VRAM
        except Exception:
            pass
        self.device = kw.get("device", "cpu")
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
    device = getattr(config, "embed_device", "auto")
    if name not in _CACHE:
        _THREADS[0] = getattr(config, "cpu_threads", 2)
        print(f"🔄 Loading embedding model {name}" + (" on the CPU (GPU left for the chat model)" if device == "cpu" else "") + "...")
        _CACHE[name] = Embedder(name, device)
    return _CACHE[name]
