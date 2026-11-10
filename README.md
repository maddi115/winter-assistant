# Winter Assistant - agentWinter

**agentWinter** is Maddi's local AI. It talks **as Maddi**, in first person.
On screen: **neon pink** = pulled from a memory vessel, **neon green** = Maddi's own words from chat data.
Questions about Maddi are answered with **Maddi's real words** (with citations).
The AI never writes those answers. It only picks numbers.

## How a message is answered

1. **Exact fact?** ("what's your name?") → answered from `memory/memory.txt`. No AI.
2. **About Maddi?** ("do you like burritos?") → the **Evidence-Transport-Model**:
   1. Search your messages twice: by meaning (LanceDB + Qwen3 embeddings) and by rare words (gradient search).
   2. Merge both lists by rank, then rerank (meaning + keywords).
   3. **Stasis gate**: if the results don't agree → "idk" in your voice.
   4. **Clear winner?** → answer with no AI.
   5. **Close call?** → the AI picks numbers (`[1,3]`), 3 times. Majority wins. If the votes split → "idk".
   6. Rules decide yes / no / unclear: feelings ("I love it"), actions ("I fell off my bike"),
      "do you have X" needs "my X", "X or Y?" compares both. Newest message wins if you changed your mind.
   7. Your exact words are pasted in, with citations like `[1] twitch · 2025-06-12`.
   8. **Threads:** the messages right before and after each quote (same channel, within 3 minutes)
      are shown under it, so short quotes like "and my family too" make sense.
3. **Anything else** (small talk, how-to, ideas) → the AI chats normally, as you.

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

ollama pull qwen3.5:4b

# import your messages (only text, author, source and date are kept)
python tools/import_chats.py path/to/chat_messages.csv --source twitch

python main.py
```

First run on a new PC (embedding model not downloaded yet):
`WINTER_ALLOW_DOWNLOAD=1 python main.py`

## Test it

```bash
python tests/test_transport_offline.py        # no Ollama needed
python tools/ask.py "do you like burritos?"   # shows the route + stasis scores
python tools/ask.py --file questions.txt      # your 30-question test
```

`tools/ask.py` prints how each answer was made (`fact`, `algo`, `ai_pick`, `idk_*`, `general`)
and how many needed no AI at all.

## Settings (`config.json`)

| Key | What it does |
|---|---|
| `model_name` | Ollama model (`qwen3.5:4b`; try `qwen3.5:0.8b` or `qwen3:8b`) |
| `transport_mode` | `algo` = no AI, `pick` = AI picks numbers, `write` = AI writes a short line too |
| `votes` | Picker votes on close calls (3; set 1 for strong models) |
| `stability_min`, `confidence_min` | Stasis gate. **Tune these with your 30-question test** |
| `owner_handles` | Your usernames. Only their messages can be spoken as "I" |
| `persona_name`, `agent_label` | Who the AI speaks as, and its honest label |
| `debug` | `true` prints route, stability, confidence and votes after each answer |

## Folders

```
core/        config, embedder, Ollama client, general chat (persona)
storage/     LanceDB conversations + evidence store (JSONL fallback)
retrieval/   gradient search, stasis gate, evidence search, chat-memory RAG
transport/   classify, packer, picker, verdict, checker, renderer, templates, engine
adapters/    decides who answers each message
tools/       import_chats.py, ask.py
tests/       offline tests
```

Borrowed from Maddi's other repos:
gradient search and the first transport model (maddis-rag);
stasis scoring, the gate thresholds and the 60/40 rerank (maddis-probability-stasisv2).

## License

MIT

## Twitch bot (agentWinter in chat)

```bash
python tools/twitch_bot.py --login      # once, signed in as the bot account
python tools/twitch_bot.py --dry-run    # practice: type "name: message", /quiet = silence
python tools/twitch_bot.py              # live in twitch_channels
```

```
chat message ─▶ room history (everyone's last messages)
              ─▶ talk.py: should I say something?
                   direct (@me, reply, "winter", meow) ─ always
                   only one person chatting ─────────── always
                   busy chat ─────────────────────────── sometimes (twitch_chime_chance, twitch_chime_gap)
                   aimed at someone else ─────────────── never
              ─▶ brain.py: same pipeline as the terminal (facts, private, my quotes, AI)
                   the AI sees the room + memory/personality.md
              ─▶ cleanup: 1 quote, short, lowercase, no "!", no "never say" lines, no links
              ─▶ send

on my own (twitch/self_talk.py) - max 3 an hour, 10 min apart, never double texting:
   chat goes quiet after a real convo ─▶ one line about what people said
   a regular comes back after 3h+     ─▶ sometimes a quick "yo welcome back"

chatters (twitch/chatters.py) - saved in twitch_chatters.json on your PC only:
   first/last seen, how often they chat, what they talk about, last 5 lines
   the AI knows it quietly ("don't recite it"); anyone can type !forgetme
```

`memory/personality.md` is how I talk. Edit it any time - it reloads by itself.
Facts about me never come from that file, only from my real messages.
