"""Speaking up uninvited = the Evidence-Transport-Model again.

  1. the algorithm finds up to 5 of MY real messages that fit what chat is saying   (no AI)
  2. the AI only picks a number, or 0 for "none fit" - asked 3 times, 2 must agree  (AI picks)
  3. my exact words are sent (cleaned like the terminal: no @mentions)               (no AI)
  4. none fit -> one sentence built ONLY from those messages, checked word by word  (synth.check)
  5. that fails too -> silence

Research note: small models interrupt group chats far too often when they decide alone
(Qwen3-4B false-interruption ~0.9 in When2Speak), so "none" is the default and needs agreement to beat.
"""
import json
import re
from collections import Counter

from retrieval.gradient import content_terms, stem

PICK_SCHEMA = {"type": "object", "properties": {"pick": {"type": "integer"}}, "required": ["pick"]}


def focus(room, line, n=3):
    """The message I'm reacting to + up to n recent messages on the same topic (oldest first)."""
    if line is None:
        return []
    terms = {stem(t) for t in content_terms(line.text)}
    out = []
    for l in reversed(room.recent(15, before=line)):
        if len(out) >= n:
            break
        if terms & {stem(t) for t in content_terms(l.text)}:
            out.append(l)
    return list(reversed(out)) + [line]


def candidates(searcher, text, private, used, min_sem, k=5):
    """Up to k of MY real messages about this - me talking, not questions, not private, not used yet."""
    from transport import classify
    from transport.packer import cosmetic
    if searcher is None or classify.is_private(text, private):
        return []
    out, seen = [], set()
    for x in searcher.search(text):
        t = x.get("text", "")
        if not (x.get("first_person") and not x.get("is_question") and x.get("has_anchor")):
            continue
        if x.get("sem", 0) < min_sem or classify.is_private(t, private):
            continue
        clean = cosmetic(t)
        key = clean.lower()
        if key in used or key in seen or len(clean) > 200 or len(clean.split()) < 3:
            continue
        seen.add(key)
        out.append({"num": len(out) + 1, "display": clean, "raw": t, "text": t})
        if len(out) >= k:
            break
    return out


def pick_messages(persona, chat_lines, focus_lines, cands):
    chat = "\n".join(chat_lines) or "(quiet)"
    react = "\n".join(f"{l.name}: {l.text}" for l in focus_lines)
    menu = "\n".join(f"[{c['num']}] {c['display']}" for c in cands)
    system = (
        f"You decide if {persona} would say one of their OWN old messages in Twitch chat right now.\n"
        f"Most of the time the answer is 0. Only pick a number if that message works as a natural, "
        f"relevant reply to what chat is saying right now - like {persona} typing it today.\n"
        f"Pick 0 if it's off-topic, out of date, would need context, or would be weird.\n"
        f'Reply ONLY as JSON: {{"pick": <number or 0>}}'
    )
    user = (f"Recent chat:\n{chat}\n\nWhat you'd be reacting to:\n{react}\n\n"
            f"Things {persona} really said:\n{menu}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def pick(llm, messages, n, votes=3, temperature=0.4):
    """2 of 3 must agree on the same number, else 0."""
    got = []
    for i in range(votes):
        try:
            raw = llm.chat_json(messages, PICK_SCHEMA, max_tokens=20, temperature=0.0 if i == 0 else temperature)
            p = int(json.loads(raw).get("pick", 0))
        except Exception:
            p = 0
        got.append(p if 1 <= p <= n else 0)
    top, count = Counter(got).most_common(1)[0]
    return (top if count >= 2 else 0), got


def tidy(text):
    """'content..' -> 'content.'  (my words stay my words)"""
    return re.sub(r"([.!?])\1+", r"\1", re.sub(r"\.{2,}", ".", text)).strip()
