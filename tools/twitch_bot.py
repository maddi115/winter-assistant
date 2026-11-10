#!/usr/bin/env python
"""agentWinter in Twitch chat.

  python tools/twitch_bot.py --login      # once: sign the BOT account in
  python tools/twitch_bot.py              # go live in config twitch_channels
  python tools/twitch_bot.py --dry-run    # no Twitch: type chat lines, see what it would send
                                          #   "someuser: @agentwinter do you like burritos?"
twitch_reply_all=true (default): answers every chat message like a normal viewer.
twitch_reply_all=false: only @mentions, !winter, and replies to the bot.
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from twitch.rules import Incoming, parse_event, question_for_bot, Cooldown

TWITCH_CONTEXT = ("You're chatting in Twitch chat with strangers. Reply in 1-2 short sentences "
                  "(under 300 characters), no links, no lists, never @everyone.")


def build_brain(config, no_ai=False):
    from storage.lancedb_storage import LanceDBStorage
    from adapters.conversation_adapter import ConversationAdapter
    from main import build_transport
    from twitch.brain import Brain

    config.chat_context = TWITCH_CONTEXT
    config.max_reply_tokens = config.twitch_max_reply_tokens
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

    return Brain(config, lambda mem: ConversationAdapter(storage, mem, ai or NoAI(),
                                                         transport=transport, config=config))


def log(s):
    print(time.strftime("%H:%M:%S "), s, flush=True)


def dry_run(config, brain, bot):
    print(f"\n🧪 Dry run as @{bot}. Type  user: message   (Ctrl+D to quit)\n")
    cd = Cooldown(0, 0)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        user, _, text = line.partition(":") if ":" in line else ("tester", "", line)
        user = user.strip().lower()
        m = Incoming("dryrun", "0", user, user, text.strip())
        q = question_for_bot(m, bot, config.twitch_prefix, config.twitch_ignore_users, config.twitch_reply_all)
        if q is None:
            print("   (not for the bot - ignored)")
            continue
        t0 = time.time()
        reply, route = brain.reply(user, user, q)
        cd.mark(user)
        print(f"   → @{bot}: {reply or '(nothing sent)'}   [{route} · {time.time() - t0:.1f}s]")


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
    how = "every message" if config.twitch_reply_all else f"@{bot}, {config.twitch_prefix}, and replies to it"
    log(f"🤖 @{bot} ready · answers {how}")

    cd = Cooldown(config.twitch_user_cooldown, config.twitch_global_cooldown)
    queue = asyncio.Queue(maxsize=config.twitch_max_queue)

    async def on_event(event):
        m = parse_event(event)
        q = question_for_bot(m, bot, config.twitch_prefix, config.twitch_ignore_users, config.twitch_reply_all)
        if q is None:
            return
        if not cd.ready(m.user):
            log(f"⏳ #{m.channel} {m.user} on cooldown: {q[:60]}")
            return
        cd.mark(m.user)                     # counts from when they asked
        try:
            queue.put_nowait((m, q))
        except asyncio.QueueFull:
            log(f"🚦 busy, skipped {m.user}: {q[:60]}")

    async def worker():
        while True:
            m, q = await queue.get()
            t0 = time.time()
            try:
                reply, route = await asyncio.to_thread(brain.reply, m.user, m.name, q)
            except Exception as e:
                log(f"❌ answer failed for {m.user}: {e}")
                continue
            if not reply:
                log(f"🚫 #{m.channel} {m.user}: {q[:60]} -> nothing safe to send [{route}]")
                continue
            await asyncio.sleep(cd.wait_global())
            sent, why = await asyncio.to_thread(helix.send, m.channel_id, bot_id, reply, m.message_id)
            cd.mark(m.user)
            mark = "💬" if sent else f"⚠️  not sent ({why})"
            log(f"{mark} #{m.channel} {m.user}: {q[:60]}\n          -> {reply}   [{route} · {time.time() - t0:.1f}s]")

    work = asyncio.create_task(worker())
    try:
        await listen(helix, bot_id, channels, on_event, log)
    finally:
        work.cancel()


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
