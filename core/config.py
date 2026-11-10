"""Configuration management - all settings in one place"""
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import List
import json


@dataclass
class Config:
    """System configuration (config.json overrides these defaults)"""
    # Storage
    db_path: str = "lance_db"
    storage_path: str = "storage"
    conv_history_path: str = "conversations_fallback"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"

    # LLM (Ollama)
    model_name: str = "qwen3.5:4b"
    temperature: float = 0.7
    num_ctx: int = 4096
    llm_timeout: int = 90             # seconds before giving up on Ollama
    think: bool = False
    max_reply_tokens: int = 512

    # Conversation memory (RAG over past Winter chats)
    rag_recent_limit: int = 6
    rag_semantic_limit: int = 4
    context_window: int = 4096  # kept so old configs still load

    # Persona: the agent speaks AS this person, in first person
    persona_name: str = "Maddi"
    agent_label: str = "Maddi's AI"
    owner_handles: List[str] = field(default_factory=lambda: ["agentmaddi", "madddyyyyi"])
    style_samples: int = 5

    # Evidence + transport model
    transport_mode: str = "pick"      # algo | pick | write
    votes: int = 3                    # consensus picker votes (1 = off)
    evidence_k: int = 20              # candidates from each search
    vessels_k: int = 5                # vessels shown to the picker
    stability_min: float = 0.60       # stasis gate
    confidence_min: float = 0.45      # stasis gate
    winner_margin: float = 0.10       # clear-winner gap between #1 and #2
    agree_skip: bool = True           # yes/no: top 3 agree -> answer without the AI
    idk_mode: str = "ai"              # no evidence: "ai" = AI replies without inventing facts, "template" = plain idk
    opener_max_words: int = 10        # pick mode
    write_max_words: int = 25         # write mode
    debug: bool = False               # print route / stasis / votes after each answer

    @classmethod
    def load(cls, config_path: str = "config.json"):
        path = Path(config_path)
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
        except Exception as e:
            print(f"⚠️  config.json unreadable ({e}), using defaults")
            return cls()
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            print(f"⚠️  Ignoring unknown config keys: {', '.join(sorted(unknown))}")
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, config_path: str = "config.json"):
        with open(config_path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)
