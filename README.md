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

**Home vs guest.** The bot's own channel is HOME (chats freely). Any other channel in
`twitch_channels` is GUEST - a polite regular: answers @agentwinterrr / "agentwinter" / replies to it,
joins in rarely (8%, 5 min apart, and the AI must have something good or it skips), never starts
conversations, never saves chatters to disk, 10s between messages, short replies in "Replying to @x".
If Twitch drops 3 messages in a row (slow mode, AutoMod) it pauses there for 5 minutes.
Practice: `python tools/twitch_bot.py --dry-run --guest`

**Speaking up only at real moments (never a dice roll).** Uninvited, I only consider talking when:
someone asks chat a question ("anyone played this?"), chat is on a topic I've really talked about
(checked against my real messages - private topics never count), or 4+ people spam the same reaction
(I add one 😹 / 🥀 / W). Even then it's a maybe, the AI can skip, and there's a budget:
2 per 15 min in someone else's chat, 4 at home. Plain chat ("good so far", "let sam drive") never gets a reply.
Tune it in config.json: `twitch_moment_*`, `twitch_budget_15min_*`, `twitch_topic_min_sem`.

**When it speaks up, it's grounded in the TWITCH CHAT - same architecture, different source.**
My own chat history is never in that prompt. `twitch/chatflow.py`:
1. pertinent chat: reactions/emotes/bots dropped, two searches (meaning + rare words) over recent chat -> up to 6 numbered lines
2. stasis gate: 3+ people, the meaning scores agree; touchy topics (sex, race, religion, politics, drugs...) -> stays out
3. the AI picks the lines + a reaction (agree / joke / answer / skip) - 3 votes, 2 must agree, skip wins ties
4. one short line from those lines, in my learned style (`memory/style.md`) + personality
5. word check (nothing chat didn't say - no new names/numbers), never about itself, "makes sense?" vote (2 of 3)
Anything fails -> silence. In someone else's chat it starts in **shadow mode** (`twitch_shadow_guest`):
speaking up is only logged as 🫥 until you've read the log and turn it off.

**Its voice.** `tools/learn_style.py` learns how I type from my messages (stats + word lists only, never the
messages) -> `memory/style.md`. `memory/personality.md` is the attitude: deadpan, quick, light teasing.
In public it's just "i" - never names me, doesn't bring up being an AI (honest if someone sincerely asks).

**Emotes.** It learns the emotes a chat actually uses (2+ people, last 30 min) and may use one -
never the streamer's sub emotes (Twitch marks them). Waves are joined with the room's own emote.
Meows: 40% at home / 20% as a guest, never twice within 45s / 3 min.

**Not replying to everything.** Emote-only messages (ICANT, KEKW, omg, 😹) are reactions - ignored unless
they're aimed at me. At home in a 1-on-1 the AI may answer "skip"; direct questions and tags always get an
answer. Fast chat (20+/min) -> I join in less; flying chat (60+/min) -> only when talked to.
Never more than 3 messages per 30 seconds. The AI gets a cheat sheet for emotes it sees (ICANT = dying laughing).
Emojis I may use are listed in `memory/personality.md` (😹 🥀) - optional, at most one per message.

`memory/personality.md` is how I talk. Edit it any time - it reloads by itself.
Facts about me never come from that file, only from my real messages.
