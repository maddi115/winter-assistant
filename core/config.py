"""Configuration management - all settings in one place"""
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import List, Optional
import json


@dataclass
class Config:
    """System configuration (config.json overrides these defaults)"""
    # Storage
    db_path: str = "lance_db"
    storage_path: str = "storage"
    conv_history_path: str = "conversations_fallback"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embed_device: str = "auto"       # "cpu" frees ~1.2GB of GPU (needed to fit a 9B chat model on 8GB)
    cpu_threads: int = 2             # cores each CPU model (embedder, VAD, Moonshine) may use - stops them hogging all of them

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
    style_file: str = "memory/style.md"   # how I type, learned from my messages (tools/learn_style.py)
    public_persona: bool = False      # true (Twitch): just "i" - never names the owner, doesn't bring up being an AI
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
    twitch_chime_gap: int = 120        # busy chat: at least this many seconds between uninvited messages
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
    # GUEST channels = any channel that isn't the bot's own. Acts like a polite regular:
    # answers when talked to, rarely joins in (only with something good), never starts
    # conversations, never saves chatters to disk.
    twitch_guest_chime_chance: float = 0.15   # chance to consider joining in on a message
    twitch_guest_chime_gap: int = 300         # at least this many seconds between joining in
    twitch_guest_min_gap: int = 10            # seconds between ANY two bot messages in a guest channel
    twitch_guest_max_words: int = 15          # AI lines
    twitch_guest_quote_chars: int = 200       # quotes from my messages
    twitch_guest_reply_thread: bool = True    # "Replying to @x" so it's clear who I'm answering
    # not replying to everything (home channel)
    twitch_home_reply_gap: int = 6        # 1-on-1: a message this soon after my last one isn't answered unless it's for me
    twitch_noise_skip: float = 0.7        # 1-on-1: chance to let a tiny message ("tacos", "yo") pass without a reply
    # busy chat (any channel)
    twitch_busy_mpm: int = 20             # messages per minute where chat counts as busy -> I join in much less
    twitch_flying_mpm: int = 60           # chat this fast -> I only answer when someone talks to me
    twitch_burst_max: int = 3             # at most this many bot messages...
    twitch_burst_window: int = 30         # ...in this many seconds, all channels together
    twitch_show_chat: bool = True         # terminal shows every chat message it reads (👀) + why it stayed quiet
    # joining in only at real MOMENTS (twitch/talk.py) - never at random
    # read the room (twitch/read_room.py): every so often read the last 15 real messages as a whole
    twitch_read_room: bool = True
    twitch_look_new: int = 8              # new real messages needed before I read the room again
    twitch_look_gap_guest: int = 60       # seconds between reads in someone else's chat
    twitch_look_gap_home: int = 45
    twitch_look_lines: int = 15
    twitch_look_fresh: int = 90           # the live conversation must have a line from the last 90s
    twitch_look_min_sure: float = 0.7     # the writer's own "how sure am I" - under this = quiet
    twitch_look_min_score: int = 4        # coherence votes: every score (topic/regular/sense/adds) at least this
    twitch_review_file: str = "twitch_review.txt"   # every line I said / would say, with the chat around it
    twitch_moment_catchup: float = 0.7    # "what are they doing?" -> fill them in from what the streamer said
    twitch_moment_question: float = 0.6   # someone asks chat a question ("anyone played this?")
    twitch_moment_topic: float = 0.0      # chat talks about something I've really talked about
    twitch_moment_wave: float = 0.5       # 4+ people spamming the same reaction -> one 😹 / 🥀 / W
    twitch_topic_min_sem: float = 0.55    # how close my real message has to be (higher = stricter)
    twitch_wave_gap: int = 180            # seconds between joining waves
    twitch_meow_gap: int = 180            # seconds between meows in someone else's chat
    twitch_budget_15min_guest: int = 3    # max uninvited messages per 15 min in someone else's chat
    twitch_budget_15min_home: int = 4     # ...and in my own
    twitch_moment_free_ai: bool = False   # question to chat + none of my messages fit -> AI writes anyway (off = silence)
    twitch_picker_votes: int = 3          # my-words picker: asked 3 times, 2 must agree on the same message
    twitch_consider_gap: int = 40         # a moment I stayed quiet on -> wait this long before considering another
    # speaking up is grounded in the TWITCH CHAT (twitch/chatflow.py) - my own chats never go in that prompt
    twitch_thread_people: int = 2         # a conversation needs at least this many different people
    twitch_chat_stability: float = 0.4    # stasis gate on the chat lines (meaning scores agree)
    twitch_chat_confidence: float = 0.3
    twitch_chat_summary: bool = True      # one line of "what's going on" for the writer (1 extra AI call, only when about to write)
    twitch_new_words: int = 2             # words the line may add that chat didn't say ("customs gave him an accessory")
    twitch_sense_check: bool = True       # final "does this make sense right now?" vote (2 of 3)
    twitch_shadow_guest: bool = True      # someone else's chat: speaking up is only LOGGED (🫥), not sent - review first
    twitch_shadow_home: bool = False      # my own chat: speaking up is sent
    twitch_third_party_emotes: bool = False  # BTTV/7TV words (ICANT, KEKW, HUH): off = only Twitch's own emotes (render for everyone)
    twitch_shadow_emotes: bool = False    # emote-only reactions (LUL, ICANT, 😹) skip shadow - they ARE sent, words stay shadowed
    twitch_pick_max_lines: int = 5        # the picker grabbing more lines than this = "no real conversation" -> skip
    twitch_quote_min_words: int = 5       # answers about me shorter than this (like "For real, I thin.") aren't sent
    twitch_stream_info: bool = True       # read the stream title + category so it knows what's on screen
    # chat mood -> one emote (twitch/mood.py) - its own budget, separate from words
    twitch_moment_mood: float = 0.6       # chance to react when 2+ people share a mood
    twitch_mood_people: int = 2           # 2 people laughing together is already a moment (one emote is low-risk)
    twitch_mood_seconds: int = 30
    twitch_emote_gap: int = 180           # seconds between my emote reactions
    twitch_emote_per_15min_guest: int = 4
    twitch_emote_per_15min_home: int = 6
    # hearing the streamer (twitch/hearing.py) - a HINT next to chat, never the only reason to speak
    twitch_audio_channels: List[str] = field(default_factory=list)   # channels to listen to (only with consent)
    twitch_audio_model: str = "moonshine/base"   # CPU, ~1 core, ~0.5GB RAM. try "moonshine/tiny" on a slow PC
    twitch_audio_arch: Optional[str] = "base"       # moonshine-voice size: tiny | base | small | medium (medium = its default, VERY heavy on CPU)
    twitch_audio_window: int = 8          # seconds of audio per piece
    twitch_audio_min_speech: float = 0.25 # less speech than this in a piece = music / game -> skipped
    twitch_audio_keep: int = 60           # seconds of what the streamer said that I remember
    # never speak up (uninvited) when chat is on these - too easy to go wrong in someone else's chat
    twitch_avoid_topics: List[str] = field(default_factory=lambda: [
        "gay", "lesbian", "straight", "trans", "sex", "sexy", "horny", "peg", "pegging", "porn", "nude", "nudes",
        "strip", "dick", "pussy", "boobs", "hoe", "slut", "rape", "race", "racist", "black", "white", "asian",
        "mexican", "indian", "arab", "jew", "jewish", "muslim", "christian", "religion", "god", "politics",
        "trump", "biden", "democrat", "republican", "election", "vote", "weed", "drugs", "drunk", "high",
        "cocaine", "kill", "die", "dead", "suicide", "gun", "shoot", "fat", "ugly", "skinny", "weight",
        "autism", "autistic", "retard", "middle-eastern", "immigrant", "illegal",
        "sexual", "sexually", "sexo", "twerk", "twerking", "pervert", "perverts", "assault", "assaulted", "molest",
        "teabag", "tea bag", "teabagging", "ass", "butt", "booty", "panties", "underwear", "thong", "cuck",
        "cucking", "down there", "busst", "bust", "cum", "smell", "smells", "saudi", "arab", "arabian",
        "culture", "wife", "gooner", "simp"])
    # meows, calmer
    twitch_meow_chance_home: float = 0.4  # chance to meow back at all (home)
    twitch_meow_chance_guest: float = 0.2 # ...in someone else's chat
    twitch_meow_gap_home: int = 45        # seconds between meows at home (twitch_meow_gap is the guest one)
    # human timing
    twitch_typing_delay: bool = True      # wait a moment like I'm typing before sending
    twitch_stale_lines: int = 6           # this many new messages since the moment -> chat moved on, don't send
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
