#!/usr/bin/env python
"""agentWinter in Twitch chat - hangs out like a regular.

  python tools/twitch_bot.py --login      # once: sign the BOT account in
  python tools/twitch_bot.py              # go live in config twitch_channels
  python tools/twitch_bot.py --dry-run    # no Twitch: type chat lines yourself
                                          #   someuser: yo whats good
                                          #   /quiet   (pretend chat went silent)
                                          #   /later   (pretend 3 hours passed - regulars come back)

When it answers: twitch/talk.py · when it starts talking on its own: twitch/self_talk.py
Who it remembers: twitch/chatters.py · how it talks: memory/personality.md
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
from twitch.talk import decide
from twitch.self_talk import SelfTalk
from twitch.chatters import Chatters

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


JOIN_IN = {"chimed in", "meow"}          # not asked directly -> counts toward the join-in gap
THREAD = {"direct", "said my name"}       # answers to someone -> may use "Replying to @x"


MAY_SKIP = {"1-on-1"}                      # not talked to directly -> the AI may decide it's not worth a reply


def answer(brain, m, q, why, room, line, note):
    """Asked directly -> full pipeline, always answers. Joining in / 1-on-1 -> the AI may skip."""
    if why == "chimed in":
        return brain.self_line(room, "chime", m.name, note, q), "chime"
    return brain.reply(m.user, m.name, q, room, line, note, may_skip=why in MAY_SKIP)


def logged_in_name(config):
    """The bot account from twitch_token.json (no network), else winterrs0."""
    try:
        import json
        return json.loads(Path(config.twitch_token_file).read_text()).get("login") or "winterrs0"
    except Exception:
        return "winterrs0"


def log(s):
    print(time.strftime("%H:%M:%S "), s, flush=True)


def dry_run(config, brain, bot, guest=False):
    where = "someone else's channel (guest)" if guest else "my own channel (home)"
    print(f"\n🧪 Dry run as @{bot} in {where}.  user: message  ·  /quiet = silence  ·  /later = 3h pass  ·  Ctrl+D quits\n")
    room = Room("dryrun", guest=guest)
    people = Chatters(None)                 # dry run never writes your chatter file
    me = SelfTalk(config, clock=room.clock)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        if raw == "/quiet":
            if room.lines:
                room.lines[-1].ts -= config.twitch_idle_sec + 1
            if me.silence(room):
                room.idle_spoken = True
                said = brain.self_line(room, "silence")
                print(f"   💭 @{bot} (on my own): {said or '(nothing worth saying)'}")
                if said:
                    me.record(room)
                    room.add(bot, bot, said, is_bot=True)
            else:
                print("   (stays quiet: not enough chat yet, or talked on my own recently)")
            continue
        if raw == "/later":
            gone = config.twitch_welcome_back_sec + 1
            for p_ in people.people.values():
                p_["last_seen"] -= gone
                p_["first_seen"] -= gone
            for l in room.lines:
                l.ts -= gone
            room.last_chime -= gone
            room.last_bot -= gone
            me.sent.clear()
            print("   (3 hours later...)")
            continue
        user, _, text = raw.partition(":") if ":" in raw else ("tester", "", raw)
        user = user.strip().lower()
        m = Incoming("dryrun", "0", user, user, text.strip())
        line = room.add(m.user, m.name, m.text)
        q, why = decide(m, bot, config, room)
        away = people.seen(m.user, m.name, m.text, talked_to_me=q is not None)
        note = people.note(m.user, away)
        if q is None:
            if me.welcome(room, m.user, away, already_answering=False):
                said = brain.self_line(room, "welcome", m.name, note)
                print(f"   💭 @{bot} (welcome back): {said or '(nothing worth saying)'}")
                if said:
                    me.record(room)
                    room.add(bot, bot, said, is_bot=True)
            else:
                print(f"   (stays quiet: {why})")
            continue
        t0 = time.time()
        reply, route = answer(brain, m, q, why, room, line, note)
        if not reply and why in MAY_SKIP:
            print(f"   (stays quiet: didn't need a reply · {route} · {time.time() - t0:.1f}s)")
            continue
        if reply:
            room.add(bot, bot, reply, is_bot=True)
            if why in JOIN_IN:
                room.last_chime = room.clock()
        print(f"   → @{bot}: {reply or '(nothing worth saying)'}   [{why} · {route} · {time.time() - t0:.1f}s]")
    print(f"\n🧠 remembered: " + "; ".join(people.note(u) for u in people.people))


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
    rooms = {login: Room(login, guest=(login != bot)) for login in channels}
    ids = dict(channels)
    # my own channel: chatters saved to disk.  someone else's: only in memory while running
    home_people = Chatters(config.twitch_chatters_file if config.twitch_remember_chatters else None)
    guest_people = Chatters(None)
    me = SelfTalk(config, clock=time.time)
    log(f"🧠 remembering {len(home_people.people)} chatters from my own channel")
    for login, room in rooms.items():
        log(f"   #{login}: " + ("GUEST - answers when talked to, rarely joins in, never starts talking"
                              if room.guest else "HOME - chats freely"))

    def people_for(room):
        return guest_people if room.guest else home_people
    log(f"🤖 @{bot} ready · personality: {config.personality_file}")

    cd = Cooldown(config.twitch_user_cooldown, config.twitch_global_cooldown)
    queue = asyncio.Queue(maxsize=config.twitch_max_queue)

    burst = []                              # when I sent, all channels together

    async def say(channel, text, reply_to=None):
        room = rooms[channel]
        if time.time() < room.muted_until:
            return False, "paused - Twitch kept dropping my messages here"
        now = time.time()
        burst[:] = [t for t in burst if now - t < config.twitch_burst_window]
        if len(burst) >= config.twitch_burst_max:
            return False, f"skipped - already sent {config.twitch_burst_max} in {config.twitch_burst_window}s"
        wait = cd.wait_global()
        if room.guest:                      # polite pace in someone else's chat
            wait = max(wait, config.twitch_guest_min_gap - (time.time() - room.last_bot))
        await asyncio.sleep(max(0.0, wait))
        thread = config.twitch_guest_reply_thread if room.guest else config.twitch_reply_thread
        sent, why = await asyncio.to_thread(helix.send, ids[channel], bot_id, text,
                                            reply_to if thread else None)
        cd.mark(bot)
        if sent:
            burst.append(time.time())
            room.drops = 0
            room.add(bot, bot, text, is_bot=True)
        else:
            room.drops += 1
            if room.drops >= 3:             # slow mode / followers-only / AutoMod - back off, don't spam retries
                room.muted_until = time.time() + 300
                room.drops = 0
                log(f"⏸️  #{channel}: Twitch dropped 3 in a row ({why}) - pausing 5 min")
        return sent, why

    async def on_event(event):
        m = parse_event(event)
        room = rooms.get(m.channel)
        if room is None or m.user == bot:
            return                          # my own messages are added when I send them
        if m.text.strip().lower() == "!forgetme":
            people_for(room).forget(m.user)
            room.lines = type(room.lines)((l for l in room.lines if l.user != m.user), maxlen=room.lines.maxlen)
            log(f"🧽 forgot {m.user}")
            await say(m.channel, f"done, forgot everything about u {m.name}")
            return
        line = room.add(m.user, m.name, m.text)
        q, why = decide(m, bot, config, room)
        people = people_for(room)
        away = people.seen(m.user, m.name, m.text, talked_to_me=q is not None) \
            if config.twitch_remember_chatters else 0.0
        note = people.note(m.user, away) if config.twitch_remember_chatters else None
        if q is None:
            if me.welcome(room, m.user, away, already_answering=False):
                try:
                    queue.put_nowait(("welcome", m, None, line, "welcome back", note))
                except asyncio.QueueFull:
                    pass
            return
        if not cd.ready(m.user):
            log(f"⏳ {m.user} on cooldown: {q[:60]}")
            return
        cd.mark(m.user)
        if why in JOIN_IN:                  # counts even if the AI ends up skipping - stay rare
            room.last_chime = room.clock()
        try:
            queue.put_nowait(("reply", m, q, line, why, note))
        except asyncio.QueueFull:
            log(f"🚦 busy, skipped {m.user}: {q[:60]}")

    async def worker():
        while True:
            kind, m, q, line, why, note = await queue.get()
            t0 = time.time()
            room = rooms[m.channel]
            if kind == "welcome":
                said = await asyncio.to_thread(brain.self_line, room, "welcome", m.name, note)
                if said and me.allowed(room):
                    sent, err = await say(m.channel, said)
                    me.record(room)
                    log(f"{'💭' if sent else '⚠️ '} welcome back {m.user} -> {said}")
                continue
            try:
                reply, route = await asyncio.to_thread(answer, brain, m, q, why, room, line, note)
            except Exception as e:
                log(f"❌ answer failed for {m.user}: {e}")
                continue
            if not reply:
                log(f"🤐 {m.user}: {q[:60]} -> nothing worth saying [{route}]")
                continue
            sent, err = await say(m.channel, reply, m.message_id if why in THREAD else None)
            mark = "💬" if sent else f"⚠️  not sent ({err})"
            log(f"{mark} {m.user}: {q[:60]}\n          -> {reply}   [{why} · {route} · {time.time() - t0:.1f}s]")

    async def self_watch():
        while True:
            await asyncio.sleep(15)
            home_people.save()              # remember chatters even if the PC crashes
            for ch, room in rooms.items():
                if me.silence(room) and queue.empty():
                    room.idle_spoken = True
                    said = await asyncio.to_thread(brain.self_line, room, "silence")
                    if said:
                        sent, err = await say(ch, said)
                        me.record(room)
                        log(f"{'💭' if sent else '⚠️ '} #{ch} on my own -> {said}")

    tasks = [asyncio.create_task(worker()), asyncio.create_task(self_watch())]
    try:
        await listen(helix, bot_id, channels, on_event, log)
    finally:
        for t in tasks:
            t.cancel()
        home_people.save()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="sign the bot account in")
    ap.add_argument("--dry-run", action="store_true", help="no Twitch, type messages yourself")
    ap.add_argument("--no-ai", action="store_true", help="algorithm only (with --dry-run)")
    ap.add_argument("--bot", default=None, help="bot name for --dry-run (default: the logged-in account)")
    ap.add_argument("--guest", action="store_true", help="--dry-run as if in someone else's channel")
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
        dry_run(config, brain, args.bot or logged_in_name(config), guest=args.guest)
        return
    try:
        asyncio.run(live(config, brain))
    except KeyboardInterrupt:
        print("\n👋 agentWinter left chat")


if __name__ == "__main__":
    main()
