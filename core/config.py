"""Configuration management - all settings in one place"""
from dataclasses import dataclass
from pathlib import Path
import json

@dataclass
class Config:
    """System configuration"""
    db_path: str = "lance_db"
    storage_path: str = "storage"
    conv_history_path: str = "conversations_fallback"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    model_name: str = "LFM2.5-1.2B"
    temperature: float = 0.7
    rag_recent_limit: int = 5
    context_window: int = 4096

    @classmethod
    def load(cls, config_path: str = "config.json"):
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                try:
                    data = json.load(f)
                    return cls(**data)
                except:
                    return cls()
        return cls()

    def save(self, config_path: str = "config.json"):
        with open(config_path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)
