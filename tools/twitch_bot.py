#!/usr/bin/env python
"""agentWinter in Twitch chat - hangs out like a regular.

  python tools/twitch_bot.py --login      # once: sign the BOT account in
  python tools/twitch_bot.py              # go live in config twitch_channels
  python tools/twitch_bot.py --dry-run    # no Twitch: type chat lines yourself
                                          #   someuser: yo whats good
                                          #   /quiet   (pretend chat went silent)

How it decides to talk: see twitch/talk.py.   How it talks: memory/personality.md
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from twitch.rules import Incoming, parse_event, Cooldown
from twitch.room import Room
from twitch.talk import decide, should_break_silence

TWITCH_CONTEXT = ("You're a regular person hanging out in Twitch chat, NOT an assistant. "
                  "Type like a real chatter: lowercase, usually 2-12 words, no emojis, no exclamation marks, "
                  "slang is fine. Don't greet formally, don't offer help, don't end with 'what's up?' "
                  "or 'how about you?'. React to what chat is actually saying, like a friend would. "
                  "No links, no lists, never @everyone.")


def build_brain(config, no_ai=False):
    from storage.lancedb_storage import LanceDBStorage
    from adapters.conversation_adapter import ConversationAdapter
    from main import build_transport
    from twitch.brain import Brain

    config.max_reply_tokens = config.twitch_max_reply_tokens
    config.silent_when_unsure = True
    config.debug = False
    if no_ai:
        config.transport_mode = "algo"
    storage = LanceDBStorage(config)
    ai, llm = None, None
    if not no_ai:
        from core.ai_engine import OllamaAI
        ai = OllamaAI(config)
        llm = ai.model
    transport, style = build_transport(config, storage, llm)
    if ai:
        ai.style = style

    class NoAI:
        def generate(self, *_):
            yield "(general chat is off with --no-ai)"

    return Brain(config, lambda mem: ConversationAdapter(storage, mem, ai or NoAI(), transport=transport,
                                                         config=config),
                 ai=ai, base_context=TWITCH_CONTEXT)


def log(s):
    print(time.strftime("%H:%M:%S "), s, flush=True)


def dry_run(config, brain, bot):
    print(f"\n🧪 Dry run as @{bot}.  Type  user: message   ·  /quiet = chat goes silent  ·  Ctrl+D quits\n")
    room = Room("dryrun")
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        if raw == "/quiet":
            if room.lines:
                room.lines[-1].ts -= config.twitch_idle_sec + 1
            if should_break_silence(room, config):
                said = brain.break_silence(room)
                print(f"   → @{bot} (breaking the silence): {said or '(nothing worth saying)'}")
                room.idle_spoken = True
                if said:
                    room.add(bot, bot, said, is_bot=True)
            else:
                print("   (not enough chat yet to start talking)")
            continue
        user, _, text = raw.partition(":") if ":" in raw else ("tester", "", raw)
        user = user.strip().lower()
        m = Incoming("dryrun", "0", user, user, text.strip())
        line = room.add(m.user, m.name, m.text)
        q, why = decide(m, bot, config, room)
        if q is None:
            print(f"   (stays quiet: {why})")
            continue
        t0 = time.time()
        reply, route = brain.reply(user, user, q, room, line)
        if reply:
            room.add(bot, bot, reply, is_bot=True)
            if why == "chimed in":
                room.last_chime = room.clock()
        print(f"   → @{bot}: {reply or '(nothing worth saying)'}   [{why} · {route} · {time.time() - t0:.1f}s]")


async def live(config, brain):
    from twitch.auth import Token
    from twitch.api import Helix
    from twitch.eventsub import listen

    token = Token(config.twitch_client_id, config.twitch_token_file)
    helix = Helix(config.twitch_client_id, token)
    bot, bot_id = token.login, token.user_id
    channels = helix.user_ids(config.twitch_channels)
    missing = {c.lower() for c in config.twitch_channels} - set(channels)
    if missing:
        log(f"⚠️  Channels not found: {', '.join(missing)}")
    if not channels:
        raise SystemExit("❌ No channels to join. Set twitch_channels in config.json")
    rooms = {login: Room(login) for login in channels}
    ids = dict(channels)
    log(f"🤖 @{bot} ready · personality: {config.personality_file}")

    cd = Cooldown(config.twitch_user_cooldown, config.twitch_global_cooldown)
    queue = asyncio.Queue(maxsize=config.twitch_max_queue)

    async def say(channel, text, reply_to=None):
        await asyncio.sleep(cd.wait_global())
        sent, why = await asyncio.to_thread(helix.send, ids[channel], bot_id, text,
                                            reply_to if config.twitch_reply_thread else None)
        cd.mark(bot)
        if sent:
            rooms[channel].add(bot, bot, text, is_bot=True)
        return sent, why

    async def on_event(event):
        m = parse_event(event)
        room = rooms.get(m.channel)
        if room is None or m.user == bot:
            return                          # my own messages are added when I send them
        line = room.add(m.user, m.name, m.text)
        q, why = decide(m, bot, config, room)
        if q is None:
            return
        if not cd.ready(m.user):
            log(f"⏳ {m.user} on cooldown: {q[:60]}")
            return
        cd.mark(m.user)
        if why == "chimed in":
            room.last_chime = room.clock()
        try:
            queue.put_nowait((m, q, line, why))
        except asyncio.QueueFull:
            log(f"🚦 busy, skipped {m.user}: {q[:60]}")

    async def worker():
        while True:
            m, q, line, why = await queue.get()
            t0 = time.time()
            try:
                reply, route = await asyncio.to_thread(brain.reply, m.user, m.name, q, rooms[m.channel], line)
            except Exception as e:
                log(f"❌ answer failed for {m.user}: {e}")
                continue
            if not reply:
                log(f"🤐 {m.user}: {q[:60]} -> nothing worth saying [{route}]")
                continue
            sent, err = await say(m.channel, reply, m.message_id)
            mark = "💬" if sent else f"⚠️  not sent ({err})"
            log(f"{mark} {m.user}: {q[:60]}\n          -> {reply}   [{why} · {route} · {time.time() - t0:.1f}s]")

    async def silence_watch():
        while True:
            await asyncio.sleep(15)
            for ch, room in rooms.items():
                if should_break_silence(room, config) and queue.empty():
                    room.idle_spoken = True
                    said = await asyncio.to_thread(brain.break_silence, room)
                    if said:
                        sent, err = await say(ch, said)
                        log(f"{'💭' if sent else '⚠️ '} #{ch} breaking the silence -> {said}")

    tasks = [asyncio.create_task(worker()), asyncio.create_task(silence_watch())]
    try:
        await listen(helix, bot_id, channels, on_event, log)
    finally:
        for t in tasks:
            t.cancel()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="sign the bot account in")
    ap.add_argument("--dry-run", action="store_true", help="no Twitch, type messages yourself")
    ap.add_argument("--no-ai", action="store_true", help="algorithm only (with --dry-run)")
    ap.add_argument("--bot", default="agentwinter", help="bot name for --dry-run")
    args = ap.parse_args()
    config = Config.load()
    config.twitch_client_id = os.environ.get("TWITCH_CLIENT_ID", config.twitch_client_id)

    if args.login:
        if not config.twitch_client_id:
            raise SystemExit("❌ Set twitch_client_id in config.json first (dev.twitch.tv/console)")
        from twitch.auth import device_login
        device_login(config.twitch_client_id, config.twitch_token_file)
        return
    if not args.dry_run and not config.twitch_client_id:
        raise SystemExit("❌ Set twitch_client_id in config.json first (dev.twitch.tv/console)")

    brain = build_brain(config, no_ai=args.no_ai)
    if args.dry_run:
        dry_run(config, brain, args.bot)
        return
    try:
        asyncio.run(live(config, brain))
    except KeyboardInterrupt:
        print("\n👋 agentWinter left chat")


if __name__ == "__main__":
    main()
