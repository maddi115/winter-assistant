#!/usr/bin/env python
"""agentWinter in Twitch chat - hangs out like a regular.

  python tools/twitch_bot.py --login      # once: sign the BOT account in
  python tools/twitch_bot.py              # go live in config twitch_channels
  python tools/twitch_bot.py --dry-run    # no Twitch: type chat lines yourself
                                          #   someuser: yo whats good
                                          #   /quiet   (pretend chat went silent)
                                          #   /later   (pretend 3 hours passed - regulars come back)
                                          #   /stream korean bbq w/ jennie · IRL   (set the stream title)
  python tools/twitch_bot.py --show-context   # also print the recent chat the AI saw for each reply

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
    config.public_persona = True            # just "i": never names the owner, doesn't bring up being an AI
    config.agent_label = "winter"
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
    learn_style_once(config, transport)

    class NoAI:
        def generate(self, *_):
            yield "(general chat is off with --no-ai)"

    return Brain(config, lambda mem: ConversationAdapter(storage, mem, ai or NoAI(), transport=transport,
                                                         config=config),
                 ai=ai, base_context=TWITCH_CONTEXT)


MOMENTS = {"question to chat", "chat on one topic"}   # speaking up uninvited -> grounded in the chat, may skip
JOIN_IN = MOMENTS | {"chat wave"}               # count against the budget + gap
THREAD = {"direct", "said my name", "question to chat"}   # answering someone -> "Replying to @x"


MAY_SKIP = {"1-on-1"}                      # not talked to directly -> the AI may decide it's not worth a reply


def answer(brain, m, q, why, room, line, note):
    """Asked directly -> full pipeline, always answers. Joining in / 1-on-1 -> the AI may skip."""
    if why == "chat wave":
        return q, "wave"                             # just the emoji - no AI needed
    if why in MOMENTS:
        said, route = brain.speak_up(room, line, m.name)        # my real words first
        if said is None and why == "question to chat" and brain.c.twitch_moment_free_ai:
            return brain.self_line(room, "chime", m.name, note, q), "chime"
        return said, route
    return brain.reply(m.user, m.name, q, room, line, note, may_skip=why in MAY_SKIP)


def typing_delay(reply, already):
    """Humans don't answer instantly: ~1-5s depending on length, minus time already spent thinking."""
    return max(0.0, min(5.0, 1.0 + 0.035 * len(reply or "")) - already)


def moved_on(room, line, limit):
    """Chat kept going while I was thinking -> my uninvited reply would land late. Don't send."""
    if line is None or line not in room.lines:
        return False
    after = list(room.lines)[list(room.lines).index(line) + 1:]
    return sum(1 for l in after if not l.is_bot) >= limit


def mark_spoken(room, why):
    if why in JOIN_IN:
        room.spoke_uninvited()
    if why == "chat wave":
        room.last_wave = room.clock()
    if why == "meow":
        room.last_meow = room.clock()


def logged_in_name(config):
    """The bot account from twitch_token.json (no network), else winterrs0."""
    try:
        import json
        return json.loads(Path(config.twitch_token_file).read_text()).get("login") or "winterrs0"
    except Exception:
        return "winterrs0"


SHOW_CONTEXT = False                       # --show-context: print what the AI was given for each reply


def context_block(brain, route):
    """The recent chat (and notes) the AI saw for this reply, indented for the terminal."""
    if not SHOW_CONTEXT:
        return ""
    if route in ("algo", "private", "fact", "reflex", "wave", "stranger_self", "idk_gate", "idk_empty",
                 "idk_votes", "algo_fallback"):
        return "\n          (no AI context - answered from rules / my messages)"
    body = brain.last_context or "(empty)"
    return "\n          ┌ what the AI saw:\n" + "\n".join("          │ " + l for l in body.splitlines())


def learn_style_once(config, transport):
    """memory/style.md = how I type, learned from my messages (stats only). Made once if missing."""
    if Path(config.style_file).exists() or transport is None:
        return
    try:
        from core import style
        s = style.write([r["text"] for r in transport.searcher.store.rows], config.style_file)
        print(f"✍️  learned how I type from {s['messages']} messages -> {config.style_file}")
    except Exception as e:
        print(f"⚠️  couldn't learn style: {e}")


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
        if raw.startswith("/stream "):
            room.stream = raw[8:].strip()
            print(f"   (stream is now: {room.stream})")
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
        room.note_emotes(m.user, m.text)
        q, why = decide(m, bot, config, room, knows=brain.knows, emojis=brain.personality.emojis)
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
        if why in MOMENTS:
            room.last_considered = room.clock()
        reply, route = answer(brain, m, q, why, room, line, note)
        if not reply and (why in MAY_SKIP or why in MOMENTS):
            print(f"   (stays quiet: {why} -> {route} · {time.time() - t0:.1f}s)" + context_block(brain, route))
            continue
        if reply:
            room.add(bot, bot, reply, is_bot=True)
            mark_spoken(room, why)
        print(f"   → @{bot}: {reply or '(nothing worth saying)'}   [{why} · {route} · {time.time() - t0:.1f}s]"
              + context_block(brain, route))
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
        shadow = config.twitch_shadow_guest if room.guest else config.twitch_shadow_home
        log(f"   #{login}: " + ("GUEST - answers when talked to, rarely joins in, never starts talking"
                              if room.guest else "HOME - chats freely")
            + ("  · speaking up = SHADOW (logged 🫥, not sent)" if shadow else ""))

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
        room.note_emotes(m.user, m.text, m.emote_meta, m.plain)
        q, why = await asyncio.to_thread(decide, m, bot, config, room, knows=brain.knows,
                                         emojis=brain.personality.emojis)
        if config.twitch_show_chat:
            what = "→ answering" if q is not None else f"(quiet: {why})"
            log(f"👀 #{m.channel} {m.user}: {m.text[:90]}   {what}   [room: {len(room.lines)} lines, "
                f"{room.mpm():.0f}/min]")
        people = people_for(room)
        away = people.seen(m.user, m.name, m.plain if m.plain is not None else m.text,
                           talked_to_me=q is not None) if config.twitch_remember_chatters else 0.0
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
        if why in MOMENTS:                  # short pause even if I end up quiet; the long gap only starts if I send
            room.last_considered = room.clock()
        if why == "meow":
            room.last_meow = room.clock()
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
                log(f"🤐 {m.user}: {q[:60]} -> stayed quiet [{why} -> {route}]" + context_block(brain, route))
                continue
            if why in JOIN_IN and moved_on(room, line, config.twitch_stale_lines):
                log(f"🕰️  {m.user}: {q[:60]} -> chat moved on, not sending: {reply}")
                continue
            shadow = config.twitch_shadow_guest if room.guest else config.twitch_shadow_home
            if shadow and why in JOIN_IN:
                log(f"🫥 #{m.channel} would say (shadow, not sent): {reply}   [{why} · {route}]"
                    + context_block(brain, route))
                mark_spoken(room, why)          # act like it spoke, so the budget behaves the same
                continue
            if config.twitch_typing_delay:
                await asyncio.sleep(typing_delay(reply, time.time() - t0))
            sent, err = await say(m.channel, reply, m.message_id if why in THREAD else None)
            if sent:
                mark_spoken(room, why)
            mark = "💬" if sent else f"⚠️  not sent ({err})"
            log(f"{mark} {m.user}: {q[:60]}\n          -> {reply}   [{why} · {route} · {time.time() - t0:.1f}s]"
                + context_block(brain, route))

    async def stream_watch():
        """Stream title + category, once a minute (the AI can't see the video, this helps a lot)."""
        while config.twitch_stream_info:
            try:
                info = await asyncio.to_thread(helix.channel_info, list(ids.values()))
                for login, cid in ids.items():
                    if info.get(cid) and info[cid] != rooms[login].stream:
                        rooms[login].stream = info[cid]
                        log(f"📺 #{login}: {info[cid]}")
            except Exception as e:
                log(f"⚠️  couldn't read stream info: {e}")
            await asyncio.sleep(60)

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

    tasks = [asyncio.create_task(worker()), asyncio.create_task(self_watch()), asyncio.create_task(stream_watch())]
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
    ap.add_argument("--show-context", action="store_true", help="print the recent chat the AI saw for each reply")
    args = ap.parse_args()
    global SHOW_CONTEXT
    SHOW_CONTEXT = args.show_context
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
        print("\n👋 winter left chat")


if __name__ == "__main__":
    main()
