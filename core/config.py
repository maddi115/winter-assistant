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
    agent_label: str = "agentWinter"
    owner_handles: List[str] = field(default_factory=lambda: ["agentmaddi", "madddyyyyi"])
    style_samples: int = 5            # real messages shown to the number-picker only
    style_words: str = "short, mostly lowercase, casual, chill, uses slang like lol, bro, tbh, ngl, fr"

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
    # never quoted, never answered ("that's private"). Words or phrases, edit freely.
    private_topics: List[str] = field(default_factory=lambda: [
        "ozempic", "wegovy", "semaglutide", "medication", "meds", "diagnosis", "therapy", "therapist",
        "doctor", "thyroid", "cancer", "health", "weight", "pounds", "lbs", "address", "real name",
        "password", "phone number", "where do you work", "where u work", "social security"])
    synthesis: bool = True            # last resort: one checked sentence built from several quotes
    synth_max_words: int = 25
    threads: bool = True              # show messages right before/after a quote
    thread_window_sec: int = 180      # ...within this many seconds, same channel
    thread_max: int = 2               # ...at most this many on each side
    debug: bool = False               # print route / stasis / votes after each answer
    stream_chat: bool = False         # true = stream word by word, but skips the "talks about me" check
    chat_context: str = ""            # extra line for the chat AI (the Twitch bot sets this)
    personality_file: str = "memory/personality.md"   # how I talk (edit freely)
    silent_when_unsure: bool = False  # true = say nothing instead of "lol nah." when the AI made something up

    # Twitch bot (python tools/twitch_bot.py)
    twitch_client_id: str = ""        # from dev.twitch.tv/console (Public client). Not a secret.
    twitch_channels: List[str] = field(default_factory=list)   # channels to chat in, e.g. ["yourchannel"]
    twitch_prefix: str = "!winter"    # "!winter do you like burritos?" (also answers @mentions + replies)
    twitch_reply_all: bool = True     # true = chats like a normal viewer (answers every message, not just @/!winter)
    twitch_user_cooldown: int = 4     # seconds before the same chatter gets another answer
    twitch_global_cooldown: int = 3   # seconds between any two bot messages
    twitch_reply_thread: bool = False # true = uses Twitch's "Replying to @x" (normal people mostly don't)
    twitch_humanize: bool = True      # AI lines: lowercase, no "!", no emoji spam, no "what's up?" endings
    twitch_max_queue: int = 5         # questions waiting; more than this get skipped
    twitch_max_chars: int = 450       # Twitch limit is 500
    twitch_citations: bool = False    # true = keep [1][2] in chat
    twitch_chat_memory: int = 0       # extra turns per chatter (the room history below already covers it)
    twitch_room_lines: int = 15       # recent chat lines the AI sees (everyone, not just the bot)
    twitch_one_on_one_sec: int = 120  # only one person chatting in this window -> always answer them
    twitch_chime_chance: float = 0.2  # busy chat: chance to jump in on a message not aimed at me (x2 for questions)
    twitch_chime_gap: int = 45        # busy chat: at least this many seconds between uninvited messages
    twitch_idle_sec: int = 240        # chat quiet this long after a real convo -> say one thing (0 = never)
    twitch_max_words: int = 18        # AI lines get cut to this (don't talk too much)
    twitch_max_quotes: int = 1        # quotes from my messages per chat line
    # talking on my own (twitch/self_talk.py) - kept rare on purpose
    twitch_self_talk: bool = True     # false = only ever answers, never starts talking
    twitch_self_max_per_hour: int = 3 # self-started messages per hour, per channel
    twitch_self_gap: int = 600        # seconds between self-started messages
    twitch_welcome_back_sec: int = 10800   # a regular gone this long (3h) may get a "welcome back"
    twitch_welcome_chance: float = 0.5
    # remembering chatters (twitch/chatters.py) - saved on your PC only, !forgetme wipes someone
    twitch_remember_chatters: bool = True
    twitch_chatters_file: str = "twitch_chatters.json"
    twitch_max_reply_tokens: int = 120
    twitch_ignore_users: List[str] = field(default_factory=lambda: [
        "nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot", "soundalerts", "sery_bot"])
    twitch_block_words: List[str] = field(default_factory=lambda: ["kys", "kill yourself"])  # never sent
    twitch_token_file: str = "twitch_token.json"

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
