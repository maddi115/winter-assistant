"""Speaking up = the Evidence-Transport architecture, run on the TWITCH CHAT itself.
My own chat history is never put in these prompts - only what this chat is saying right now.

  1. pertinent chat   drop reactions / emotes / bots, two searches (meaning + rare words) over
                      the recent chat lines, merge -> up to 6 numbered lines (the "vessels")   (algorithm)
  2. stasis gate      are those lines really one conversation? 3+ people, scores agree         (algorithm)
  3. AI picks         which lines are the conversation + reaction (agree/joke/answer/skip)
                      asked 3 times, 2 must agree, skip wins ties                              (AI picks)
  4. one line         written from the picked lines, in my style                               (AI writes)
  5. checks           word check against the picked lines, no claims about me,
                      banned phrases, "does this make sense right now?" (2 of 3 yes)           (rules + AI)
  anything fails -> silence
"""
import json
import re
from collections import Counter

import numpy as np

from retrieval.gradient import content_terms, stem

REACTIONS = ["skip", "agree", "joke", "answer"]
PICK_SCHEMA = {"type": "object",
               "properties": {"lines": {"type": "array", "items": {"type": "integer"}},
                              "react": {"type": "string", "enum": REACTIONS}},
               "required": ["lines", "react"]}
LINE_SCHEMA = {"type": "object", "properties": {"line": {"type": "string"}}, "required": ["line"]}
OK_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}

# filler never makes a topic or a "new fact" (from the 2-word topic rule)
COMMON = set("""
saw see seen got get gets getting go goes going went gone say says said know knew think thought make made making
want wanted like liked look looking come came take took give gave thing things stuff time times good bad better
best worse worst really very just still even also too much many more most less least than then now here there
people person guy guys man men bro dude girl today tonight tomorrow yesterday day days night week year one two
three lol lmao lmfao yeah yea yes nah nope okay right wrong sure maybe always never ever every everyone someone
anyone something anything nothing everything gotta gonna wanna kinda sorta pretty quite super amazing awesome
cool nice great fine fast slow big small little long short old new real fake true fr ngl tbh felt feel feeling
turn back away around over under again keep kept put let lets need needs try tried use used work worked help
start stop end call called talk talks talking tell told ask asked show showed watch watching play playing
honestly literally actually crazy wild insane impressive rough cursed tho though idk wtf omg dont doesnt didnt
anyway anyways whatever wait well like yeah ok okay alright because cause about with without into onto
""".split())
# words a reaction may add without chat having said them (an opinion, not a fact)
OPINION = {"crazy", "wild", "insane", "impressive", "rough", "cursed", "valid", "mid", "goated", "fire", "trash",
           "bad", "good", "funny", "weird", "sus", "brutal", "clean", "messy", "scary", "sad", "cute", "nice",
           "honestly", "lowkey", "highkey", "somehow", "apparently", "again", "already", "still", "yeah", "no"}


def topic_words(text, ignore=()):
    """Real words of a chat line - filler and names never make a topic."""
    return {stem(t) for t in content_terms(text) if len(t) > 2 and not t.isdigit()
            and t not in COMMON and stem(t) not in COMMON and t not in ignore and stem(t) not in ignore}


def room_names(room, top_share=0.1):
    """Names here (chatters, the channel, whoever chat keeps talking about) - not topics."""
    names = set()
    if room is None:
        return names
    for part in re.split(r"[_\d]+", room.channel.lower()):
        if len(part) > 2:
            names |= {part, stem(part)} | {part[:n] for n in range(5, len(part))}
    lines = [l for l in room.lines if not l.is_bot]
    for l in lines:
        names |= {l.user.lower(), stem(l.user.lower())}
    # nicknames chat keeps using ("Sam", "Jennie"): people capitalize names, not topics like "traffic"
    seen, capped = Counter(), Counter()
    for l in lines:
        for w in re.findall(r"[A-Za-z][a-z]{2,}", l.text):
            seen[w.lower()] += 1
            if w[0].isupper() and not l.text.startswith(w):
                capped[w.lower()] += 1
    names |= {w for w, n in seen.items() if n >= 3 and capped[w] / n >= 0.2}
    names |= {stem(w) for w in list(names)}
    return names


def clean_lines(room, upto, n=30):
    """Recent human chat that's actually talk: no reactions, emotes-only, bots or my own lines."""
    from twitch.emotes import is_reaction
    out = []
    for l in room.recent(n, before=upto):
        if l.is_bot or is_reaction(l.text):
            continue
        out.append(l)
    return out


def thread(room, line, embed=None, k=5):
    """Two searches over recent chat, like over my messages: rare shared words + meaning. RRF merge.
    -> (lines oldest-first incl. the trigger, sims to the trigger, vectors) or ([], [], None)"""
    pool = clean_lines(room, line)
    if not pool:
        return [line], np.array([1.0]), None
    ignore = room_names(room)
    want = topic_words(line.text, ignore)
    lex = sorted(((len(want & topic_words(l.text, ignore)), i) for i, l in enumerate(pool)), reverse=True)
    lex = [i for score, i in lex if score > 0]
    sims = np.zeros(len(pool))
    vecs = None
    if embed is not None:
        try:
            q = embed.encode_query(line.text)
            vecs = embed.encode_docs([l.text for l in pool])
            sims = vecs @ q
        except Exception:
            vecs = None
    sem = [i for i in np.argsort(-sims) if sims[i] > 0] if vecs is not None else []
    rrf = Counter()
    for ranked in (lex, sem):
        for r, i in enumerate(ranked):
            rrf[i] += 1.0 / (60 + r)
    top = sorted(i for i, _ in rrf.most_common(k))           # back to time order
    lines = [pool[i] for i in top] + [line]
    s = np.array([float(sims[i]) for i in top] + [1.0])
    v = None
    if vecs is not None:
        v = np.vstack([vecs[top]] + [embed.encode_docs([line.text])]) if top else embed.encode_docs([line.text])
    return lines, s, v


def touchy(lines, avoid) -> str:
    """The first avoid-list word in these lines, or ''."""
    pat = re.compile(r"(?<![a-z])(" + "|".join(re.escape(w) for w in avoid) + r")(?![a-z])", re.I) if avoid else None
    for l in lines:
        m = pat.search(l.text) if pat else None
        if m:
            return m.group(1).lower()
    return ""


def one_conversation(lines, sims, vecs, c, ignore=()):
    """Stasis gate on chat: 3+ different people, shared real words, and the meaning scores agree."""
    word = touchy(lines, getattr(c, "twitch_avoid_topics", []))
    if word:
        return False, f"touchy topic ({word}) - staying out of it"
    people = {l.user for l in lines}
    if len(people) < c.twitch_thread_people or len(lines) < 3:
        return False, f"only {len(people)} people on it"
    trig = topic_words(lines[-1].text, ignore)
    if len(trig) < 1:
        return False, "nothing to talk about in that message"
    sharing = sum(1 for l in lines[:-1] if trig & topic_words(l.text, ignore))
    if vecs is not None and len(sims) >= 3:
        # meaning scores (the stasis gate, like over my messages) - "drive / traffic / parking" agree
        # even without repeating a word
        from retrieval.stasis import gate
        ok, stab, conf = gate(vecs, sims, has_keyword=sharing >= 1,
                              stability_min=c.twitch_chat_stability, confidence_min=c.twitch_chat_confidence)
        if not ok:
            return False, f"chat not on one thing (stability {stab:.2f}, confidence {conf:.2f})"
        return True, f"one conversation (stability {stab:.2f}, confidence {conf:.2f})"
    if sharing < 2:                         # no meaning scores -> need 2+ other lines sharing a real word
        return False, "no shared topic"
    return True, "one conversation (shared words)"


def numbered(lines):
    return "\n".join(f"[{i}] {l.name}: {l.text[:150]}" for i, l in enumerate(lines, 1))


def pick_messages(lines):
    system = ("You read a Twitch chat and decide if a regular chatter would say something right now.\n"
              "Pick the numbers of the lines that are one conversation, and how to react:\n"
              "agree = say you agree or relate, joke = a light joke about it, answer = someone asked something "
              "and the lines give the answer, skip = nothing worth adding.\n"
              "Most of the time the answer is skip.\n"
              'Reply ONLY as JSON: {"lines": [numbers], "react": "skip|agree|joke|answer"}')
    return [{"role": "system", "content": system}, {"role": "user", "content": numbered(lines)}]


def pick(llm, msgs, n, votes=3, temperature=0.4):
    """2 of 3 must agree on the reaction (skip wins ties); lines = picked by 2+ votes."""
    reacts, ids = [], Counter()
    for i in range(votes):
        try:
            d = json.loads(llm.chat_json(msgs, PICK_SCHEMA, max_tokens=40, temperature=0.0 if i == 0 else temperature))
            r = d.get("react", "skip")
            r = r if r in REACTIONS else "skip"
            got = {int(x) for x in d.get("lines", []) if isinstance(x, (int, float)) and 1 <= int(x) <= n}
        except Exception:
            r, got = "skip", set()
        reacts.append(r)
        ids.update(got)
    top, count = Counter(reacts).most_common(1)[0]
    if count < 2 or top == "skip" or reacts.count("skip") >= count:
        return "skip", [], reacts
    picked = sorted(i for i, c_ in ids.items() if c_ >= 2) or [n]
    if n not in picked:
        picked.append(n)                     # always include what I'm reacting to
    return top, picked, reacts


def write_messages(style_prompt, lines, react):
    how = {"agree": "agree or relate with it", "joke": "make a light, low-key joke about it",
           "answer": "answer the question using what chat said"}[react]
    system = (f"You are a regular in this Twitch chat. Write ONE short message (1-8 words) that would come next.\n"
              f"{how}. Only talk about what's in these lines - don't add facts, names or numbers they don't have.\n"
              f"Never talk about yourself, your life or being an AI. No hashtags, no quotes.\n"
              f"How you type:\n{style_prompt}\n"
              'Reply ONLY as JSON: {"line": "..."}')
    return [{"role": "system", "content": system}, {"role": "user", "content": numbered(lines)}]


def grounded(reply, lines, slang=(), allow_new=1):
    """Every real word comes from the picked chat lines (or is slang / an opinion word).
    At most `allow_new` other words, and never a new number or Name."""
    have = {stem(t) for l in lines for t in content_terms(l.text)}
    have |= {w.lower() for l in lines for w in re.findall(r"[A-Za-z0-9$']+", l.text)}
    extra = []
    for w in re.findall(r"[A-Za-z0-9$']+", reply):
        low = w.lower()
        if low in have or stem(low) in have or low in COMMON or low in OPINION or low in slang:
            continue
        if len(low) <= 2 or low in {"the", "and", "for", "that", "this", "with", "its", "his", "her", "him"}:
            continue
        if re.search(r"\d", w) or (w[:1].isupper() and w.lower() != w and len(w) > 1 and not w.isupper()):
            return False                     # a new number or name = making things up
        extra.append(low)
    return len(extra) <= allow_new


SELF = re.compile(r"\b(i|i'm|im|i've|ive|i'd|i'll|my|me|mine|myself)\b", re.I)


def about_me(reply) -> bool:
    """Speaking up is about the chat, never about my own life ('i drove there yesterday')."""
    return bool(SELF.search(re.sub(r"\b[A-Z]{3,}\b", " ", reply)))   # ICANT etc. aren't "i"


def sense_messages(lines, reply):
    system = ("Would this message make sense as the next message in this Twitch chat, said by a regular? "
              "Say false if it's off-topic, weird, repeats someone, or sounds like a bot.\n"
              'Reply ONLY as JSON: {"ok": true|false}')
    return [{"role": "system", "content": system},
            {"role": "user", "content": numbered(lines) + f"\n\nNext message: {reply}"}]


def makes_sense(llm, lines, reply, votes=3):
    yes = 0
    for i in range(votes):
        try:
            yes += bool(json.loads(llm.chat_json(sense_messages(lines, reply), OK_SCHEMA, max_tokens=10,
                                                 temperature=0.0 if i == 0 else 0.4)).get("ok"))
        except Exception:
            pass
    return yes >= 2
