"""Read the room: every so often, read the LAST 15 real chat messages as a whole, work out what's
going on, and only chime in on a live conversation. Every check that fails = silence.

  due()        enough new chat + time since my last look + talking budget open
  last_real()  the last 15 messages that are actual talk (no emote spam, bots, greetings)
  read()       one AI call: what's going on, the threads, which one is live
  live()       the live thread really is live: 3+ lines, 2+ people, recent, in the newest lines
  write()      one deadpan line about that thread (+ how sure it is)
  checks       broken sentence, filler, made-up words, repeat, about itself, explain test, coherence votes
"""
import json
import re

from twitch.chatflow import numbered, topic_words, touchy, grounded, repeats_chat, about_me, stream_line

READ_SCHEMA = {"type": "object", "properties": {
    "now": {"type": "string"},
    "threads": {"type": "array", "items": {"type": "object", "properties": {
        "about": {"type": "string"}, "lines": {"type": "array", "items": {"type": "integer"}}},
        "required": ["about", "lines"]}},
    "active": {"type": "integer"}}, "required": ["now", "threads", "active"]}
WRITE_SCHEMA = {"type": "object", "properties": {"line": {"type": "string"}, "sure": {"type": "number"}},
                "required": ["line", "sure"]}
EXPLAIN_SCHEMA = {"type": "object", "properties": {"meaning": {"type": "string"},
                                                   "lines": {"type": "array", "items": {"type": "integer"}}},
                  "required": ["meaning", "lines"]}
RATE_SCHEMA = {"type": "object", "properties": {k: {"type": "integer"} for k in
                                                ("on_topic", "regular", "sense", "says_something")},
               "required": ["on_topic", "regular", "sense", "says_something"]}

FILLER = {"wtf", "smh", "real", "fr", "frfr", "true", "facts", "lol", "lmao", "bro", "bruh", "damn", "crazy",
          "thats crazy", "that's crazy", "no way", "omg", "same", "w", "l", "ok", "okay", "yeah", "nah", "fr tho",
          "real talk", "wild", "insane", "deadass", "on god", "ong", "lmaoo", "wtf smh", "tbh", "idk"}
DANGLING = {"and", "but", "or", "the", "a", "an", "to", "of", "with", "for", "is", "are", "was", "my", "ur",
            "your", "his", "her", "their", "so", "because", "cuz", "if", "when", "that", "like", "at", "in", "on"}
GREETING = re.compile(r"^\s*(hi+|hey+|hello+|yo+|sup|wsg|wsp|gm|gn|welcome|ty|thanks?|thank you)\b", re.I)


def due(room, c, guest):
    """Time to read the room? (also: is my talking budget open - no point reading if I can't speak)"""
    now = room.clock()
    gap = c.twitch_look_gap_guest if guest else c.twitch_look_gap_home
    if now - getattr(room, "last_look", -1e9) < gap:
        return False
    new = [l for l in room.lines if not l.is_bot and l.ts > getattr(room, "last_look", -1e9) and real(l.text)]
    if len(new) < c.twitch_look_new:
        return False
    speak_gap = c.twitch_guest_chime_gap if guest else c.twitch_chime_gap
    budget = c.twitch_budget_15min_guest if guest else c.twitch_budget_15min_home
    if now - room.last_chime < speak_gap or room.uninvited_since(900) >= budget:
        return False
    return True


def real(text):
    """Actual talk: not emote spam / a reaction / a greeting / only @tags."""
    from twitch.emotes import is_reaction
    bare = re.sub(r"@\w+", " ", text).strip()
    if len(bare.split()) < 2 or is_reaction(bare):
        return False
    return not GREETING.match(bare) or len(bare.split()) >= 5


def last_real(room, c, n=15):
    ignore = {u.lower() for u in getattr(c, "twitch_ignore_users", [])}
    out = [l for l in room.lines if not l.is_bot and l.user not in ignore and real(l.text)]
    return out[-n:]


def read_messages(lines, stream="", heard=()):
    system = ("You read the last messages of a Twitch chat (oldest first, numbered) plus what the streamer said.\n"
              "1. now: ONE short sentence on what's going on right now (newest lines matter most). "
              "The speech-to-text is often wrong - skip parts that sound odd.\n"
              "2. threads: the separate conversations in the chat, each with its line numbers. "
              "Lines that don't belong to a conversation are left out.\n"
              "3. active: the index (0, 1, ...) of the thread people are STILL on in the newest lines, with at "
              "least 2 different people. -1 if it's just greetings, reactions or random lines.\n"
              'Reply ONLY as JSON: {"now": "...", "threads": [{"about": "...", "lines": [numbers]}], "active": 0}')
    return [{"role": "system", "content": system}, {"role": "user", "content": stream_line(stream, heard) + numbered(lines)}]


def read(llm, lines, stream="", heard=()):
    """-> (now, threads [(about, [line numbers])], active index or -1). Never raises."""
    try:
        d = json.loads(llm.chat_json(read_messages(lines, stream, heard), READ_SCHEMA, max_tokens=300))
    except Exception:
        return "", [], -1
    n = len(lines)
    threads = []
    for t in d.get("threads", []) or []:
        ids = sorted({int(x) for x in t.get("lines", []) if isinstance(x, (int, float)) and 1 <= int(x) <= n})
        if ids:
            threads.append((str(t.get("about", ""))[:80], ids))
    active = d.get("active", -1)
    active = active if isinstance(active, int) and 0 <= active < len(threads) else -1
    return " ".join(str(d.get("now", "")).split()[:25]), threads, active


def live(lines, ids, clock_now, c):
    """The AI's 'active' thread really is live -> '' else why not."""
    picked = [lines[i - 1] for i in ids]
    if len(picked) < 3:
        return f"only {len(picked)} lines on it"
    if len({l.user for l in picked}) < 2:
        return "only one person on it"
    if max(ids) < len(lines) - 4:
        return "chat already moved on from it"
    if clock_now - max(l.ts for l in picked) > c.twitch_look_fresh:
        return "it went quiet"
    return ""


def pick_live(lines, threads, ai_pick, clock_now, c):
    """Which thread is live is decided by CODE, not the AI (the 9B kept saying 'none' even with 6 people
    on one thing). Live = 3+ lines, 2+ people, recent, in the newest lines. Newest live thread wins;
    the AI's own pick wins a tie. -> (index or -1, why not)"""
    ok, reasons = [], []
    for i, (_, ids) in enumerate(threads):
        why = live(lines, ids, clock_now, c)
        if why:
            reasons.append(why)
        else:
            ok.append(i)
    if not ok:
        return -1, ("no live conversation: " + reasons[0]) if reasons else "no conversations, just random lines"
    if ai_pick in ok and max(threads[ai_pick][1]) >= max(max(threads[i][1]) for i in ok) - 2:
        return ai_pick, ""
    return max(ok, key=lambda i: (max(threads[i][1]), len(threads[i][1]))), ""


def write_messages(style_prompt, lines, ids, now, stream="", heard=(), emotes=()):
    system = ("You are a regular in this Twitch chat. Write ONE short message (1-10 words) that would come next, "
              "about the marked conversation.\n"
              "Add ONE specific detail or angle from the chat or the streamer - don't repeat what someone said. "
              "Only use what's in the chat or what the streamer said - no new names, places or numbers.\n"
              "Deadpan: say less than the moment deserves. No hype, no robot jokes, no punchline setups. "
              "Never talk about yourself, your life or being an AI. No hashtags, no quotes, no @.\n"
              "sure = how sure you are (0 to 1) this fits right now and makes sense. Be honest - "
              "if you'd have nothing good to say, write skip with sure 0.\n"
              + (f"You may end with ONE of these emotes if it fits (most messages none): {' '.join(emotes[:6])}\n"
                 if emotes else "") +
              f"How you type:\n{style_prompt}\n"
              'Reply ONLY as JSON: {"line": "...", "sure": 0.0}')
    marked = "\n".join(f"[{i}]{' *' if i in ids else '  '} {l.name}: {l.text[:150]}" for i, l in enumerate(lines, 1))
    user = (stream_line(stream, heard) + f"What's going on: {now}\n"
            "Chat (* = the conversation to react to):\n" + marked)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def broken(line):
    """Cut off / dangling / not a sentence: 'For real, I thin.' 'customs gave him and'"""
    words = re.findall(r"[A-Za-z0-9$']+", line)
    if not words:
        return "empty"
    if words[-1].lower() in DANGLING:
        return f"ends on '{words[-1]}'"
    if re.search(r"[A-Za-z]{2,}-$|\.\.\.\s*\w{1,2}$", line.strip()):
        return "cut off"
    caps = [w for w in words if w.isupper() and len(w) > 3]
    if len(caps) > 1:
        return "random caps"
    return ""


def filler(line):
    t = re.sub(r"[^a-z' ]", "", line.lower()).strip()
    words = t.split()
    if not words or t in FILLER:
        return True
    return all(w in FILLER for w in words)


def explain_messages(lines, reply):
    system = ("Here is a Twitch chat (numbered) and a new message. In one short sentence, say what the new "
              "message means, and list the numbers of the chat lines it's reacting to. If it doesn't make sense "
              "or isn't about any line, say so and list no lines.\n"
              'Reply ONLY as JSON: {"meaning": "...", "lines": [numbers]}')
    return [{"role": "system", "content": system},
            {"role": "user", "content": numbered(lines) + f"\n\nNew message: {reply}"}]


def explains(llm, lines, ids, reply):
    """The explain test: can a fresh read point the reply back at the live thread? -> '' or why not"""
    try:
        d = json.loads(llm.chat_json(explain_messages(lines, reply), EXPLAIN_SCHEMA, max_tokens=80))
    except Exception:
        return "explain test errored"
    got = {int(x) for x in d.get("lines", []) if isinstance(x, (int, float))}
    meaning = str(d.get("meaning", "")).lower()
    if not got:
        return "explain test: about nothing in chat"
    if not got & set(ids):
        return "explain test: about a different conversation"
    if re.search(r"doesn'?t make sense|unclear|not clear|nonsens|random|no clear|unrelated", meaning):
        return "explain test: even the AI can't tell what it means"
    return ""


def rate_messages(lines, ids, reply, now, stream="", heard=()):
    system = ("Rate a new message for this Twitch chat, 1 (bad) to 5 (great), on:\n"
              "on_topic: clearly about what the marked conversation is on\n"
              "regular: something a real regular would type (not a bot, not cringe, not forced)\n"
              "sense: makes sense on its own, no confusing or made-up stuff\n"
              "says_something: adds something - not filler, not just repeating chat\n"
              "Be strict. Most messages are 3 or lower.\n"
              'Reply ONLY as JSON: {"on_topic": 1, "regular": 1, "sense": 1, "says_something": 1}')
    marked = "\n".join(f"[{i}]{' *' if i in ids else '  '} {l.name}: {l.text[:150]}" for i, l in enumerate(lines, 1))
    return [{"role": "system", "content": system},
            {"role": "user", "content": stream_line(stream, heard) + f"What's going on: {now}\n" + marked
             + f"\n\nNew message: {reply}"}]


def coherent(llm, lines, ids, reply, now, stream="", heard=(), votes=3, need=4):
    """Every score >= need, on 2 of 3 votes (stops early). -> (ok, scores of each vote)"""
    yes = no = 0
    seen = []
    for i in range(votes):
        try:
            d = json.loads(llm.chat_json(rate_messages(lines, ids, reply, now, stream, heard), RATE_SCHEMA,
                                         max_tokens=40, temperature=0.0 if i == 0 else 0.4))
            scores = [int(d.get(k, 0)) for k in ("on_topic", "regular", "sense", "says_something")]
        except Exception:
            scores = [0, 0, 0, 0]
        seen.append(scores)
        ok = min(scores) >= need
        yes, no = yes + ok, no + (not ok)
        if yes >= 2 or no >= 2:
            break
    return yes >= 2, seen


def look(llm, room, c, style_prompt, emotes=(), personality_prompt="", polish=None, heard_fn=None):
    """The whole thing. -> (line or None, why, log dict). Every failed check = silence."""
    lines = last_real(room, c, c.twitch_look_lines)
    info = {"lines": lines}
    stream = getattr(room, "stream", "")
    heard = heard_fn(room) if heard_fn else []
    if len(lines) < 5:
        return None, "not enough real chat", info
    now, threads, ai_pick = read(llm, lines, stream, heard)
    active, why = pick_live(lines, threads, ai_pick, room.clock(), c)
    info.update(now=now, threads=threads, active=active, ai_pick=ai_pick)
    if active < 0:
        return None, why, info
    about, ids = threads[active]
    thread_lines = [lines[i - 1] for i in ids]
    word = touchy(thread_lines + [type("L", (), {"text": h})() for h in heard], c.twitch_avoid_topics)
    if word:
        return None, f"touchy topic ({word}) - staying out of it", info
    prompt = write_messages(style_prompt + ("\n" + personality_prompt if personality_prompt else ""),
                            lines, ids, now, stream, heard, emotes)
    backed = lines + [type("L", (), {"text": h})() for h in heard] + [type("L", (), {"text": stream})()]
    slang = set(re.findall(r"[a-z']+", style_prompt.lower()))
    tries = []
    text, problem = None, ""
    for attempt in range(2):                     # one rewrite max, then silence
        try:
            d = json.loads(llm.chat_json(prompt, WRITE_SCHEMA, max_tokens=50, temperature=0.7 if attempt == 0 else 0.9))
            raw, sure = str(d.get("line", "")).strip(), float(d.get("sure", 0) or 0)
        except Exception:
            raw, sure = "", 0.0
        tries.append((raw, sure))
        problem = mechanical(raw, sure, lines, backed, slang, c)
        if not problem:
            text = raw
            break
        if problem.startswith("repeats"):
            prompt = prompt + [{"role": "assistant", "content": json.dumps({"line": raw, "sure": sure})},
                               {"role": "user", "content": "That just repeats chat. Add something of your own, "
                                                           "or skip."}]
        elif problem in ("skip", "not sure enough"):
            break
    info["tries"] = tries
    if text is None:
        return None, problem, info
    from transport.checker import claim_guard
    if not claim_guard(text):
        return None, "talked about itself", info
    if polish:
        text = polish(text)
        if not text:
            return None, "didn't pass the filters", info
        b = broken(text)                         # shortening can leave a dangling end
        if b:
            return None, f"broken sentence ({b})", info
    why = explains(llm, lines, ids, text)
    info["explain"] = why or "ok"
    if why:
        return None, why, info
    ok, scores = coherent(llm, lines, ids, text, now, stream, heard, need=c.twitch_look_min_score)
    info["scores"] = scores
    if not ok:
        return None, "coherence votes said no", info
    return text, "read the room", info


def mechanical(raw, sure, thread_lines, backed, slang, c):
    """The checks that need no AI. -> '' or the problem."""
    from twitch.brain import is_skip
    if not raw or is_skip(raw):
        return "skip"
    if sure < c.twitch_look_min_sure:
        return "not sure enough"
    if "@" in raw or len(raw) > c.twitch_max_chars:
        return "bad format"
    b = broken(raw)
    if b:
        return f"broken sentence ({b})"
    if filler(raw):
        return "just filler"
    if repeats_chat(raw, thread_lines):
        return "repeats chat"
    if not grounded(raw, backed, slang, allow_new=c.twitch_new_words):
        return "made something up (word check)"
    if about_me(raw):
        return "talked about itself"
    return ""


def log_block(info, why, said=None):
    """What it looked at + every check, for --show-context."""
    out = []
    lines = info.get("lines", [])
    if lines:
        out.append("┌ last %d:" % len(lines))
        out += [f"│ {x}" for x in numbered(lines).splitlines()]
    if info.get("now"):
        out.append(f"│ now: {info['now']}")
    if info.get("threads"):
        out.append("│ threads: " + " · ".join(f"{a} {ids}" for a, ids in info["threads"]))
        a, ai = info.get("active", -1), info.get("ai_pick", -1)
        out.append("│ live: " + (info["threads"][a][0] if a >= 0 else "none")
                   + f"   (AI's own pick: {info['threads'][ai][0] if ai >= 0 else 'none'})")
    for raw, sure in info.get("tries", []):
        out.append(f"│ wrote: {raw!r} (sure {sure:.2f})")
    if "explain" in info:
        out.append(f"│ explain test: {info['explain']}")
    if "scores" in info:
        out.append(f"│ scores (topic/regular/sense/adds): {info['scores']}")
    out.append(f"│ -> {'SAY: ' + said if said else 'quiet: ' + why}")
    return "\n".join("          " + x for x in out)
