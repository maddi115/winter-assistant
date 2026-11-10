"""Evidence-Transport-Model: the whole pipeline, AI last.

  1. classify question            (rules)
  2. search twice + merge + rerank (algorithm)
  3. stasis gate -> "idk"          (algorithm)
  4. pack vessels                  (algorithm)
  5. clear winner? -> answer       (algorithm, no AI)
  6. close call -> AI picks numbers, 3 votes  (AI)
  7. verdict + opener + render + check        (algorithm)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional

import numpy as np

from retrieval.stasis import gate
from transport import classify, templates
from transport.checker import check_opener
from transport.packer import pack
from transport.picker import build_messages, vote
from transport.renderer import render
from transport.verdict import decide, polarity, possesses, action_polarity, mentions_object, HABIT_VERBS
from retrieval.gradient import content_terms, stem


@dataclass
class TransportResult:
    text: str                        # plain (saved to history)
    route: str                       # algo | ai_pick | idk_gate | idk_votes | idk_empty
    used_ids: List[int] = field(default_factory=list)
    debug: Dict = field(default_factory=dict)
    display: str = ""                # terminal version (green quotes); falls back to text

    def shown(self) -> str:
        return self.display or self.text


class TransportModel:
    def __init__(self, config, searcher, llm=None, style_samples=None):
        self.c = config
        self.searcher = searcher
        self.llm = llm
        self.style = style_samples or []

    def _idk(self, tone, route, debug, followup=False):
        kind = "NOMORE" if followup else "IDK"
        return TransportResult(templates.pick(kind, tone), route, [], debug)

    def answer(self, question: str, exclude: Set[int] = frozenset(),
               tone_source: Optional[str] = None) -> TransportResult:
        c = self.c
        question = classify.unslang(question)              # "do u fw kombucha" -> "do u like kombucha"
        tone = classify.tone(tone_source or question)
        qtype = classify.question_type(question)
        debug = {"qtype": qtype, "tone": tone}

        # comparison: "do you like cheetos or burritos more?"
        opts = classify.compare_options(question) if not exclude else None
        if opts:
            return self._compare(question, opts, tone, debug)

        # 2. search
        cands = self.searcher.search(question, exclude)
        if exclude:   # follow-up: only messages that still share the question's words
            cands = [x for x in cands if x["has_anchor"]]
        # only things I said ABOUT MYSELF can answer a question about me:
        # first person ("I", "my", "we") and not a question I asked someone else
        cands = [x for x in cands if x["first_person"] and not x["is_question"]]
        # "did you fall off your bike?": candidates must mention the bike, not just "fall"
        qverb = classify.question_verb(question) if qtype == "yes_no" else None
        qverbs = classify.question_verbs(question) if qverb else []
        if qverb and qverb not in ("like", "love", "enjoy", "hate", "dislike", "adore", "prefer"):
            objs = [t for t in content_terms(question) if t not in {stem(v) for v in qverbs}]
            if objs:
                cands = [dict(x, has_anchor=True) for x in cands if mentions_object(x["text"], objs)]
        # "do you have a dog?" needs "my dog" / "i got a dog"
        if qtype == "yes_no" and classify.asks_possession(question):
            cands = [x for x in cands if x.get("anchor") and possesses(x["text"], x["anchor"])]
            debug["possession"] = True
        if not cands:
            return self._idk(tone, "idk_empty", debug, bool(exclude))
        top = cands[:c.vessels_k]

        # 3. stasis gate
        passed, stab, conf = gate(np.stack([x["vector"] for x in top]),
                                  [x["sem"] for x in top],
                                  has_keyword=any(x["kw"] > 0 for x in top),
                                  stability_min=c.stability_min, confidence_min=c.confidence_min)
        debug.update(stability=round(stab, 3), confidence=round(conf, 3))
        # follow-ups already passed the gate on the first ask; leftovers just need the keywords
        if not passed and not exclude:
            return self._idk(tone, "idk_gate", debug, bool(exclude))

        # 4. pack (+ thread context for the AI picker)
        vessels = pack(top, question, c.vessels_k)
        for v in vessels:
            v["context"] = self._context(v["idx"])

        # 5. clear winner?
        margin = top[0]["combo"] - (top[1]["combo"] if len(top) > 1 else 0.0)
        # the answer must contain the question's rarest word (e.g. "burrito", not "get")
        # ...or (yes/no questions only) at least 2 of the top 3 contain it: they agree,
        # and the sentiment rules double-check the verdict. Open questions ("what's your
        # favorite food?") still go to the AI, because sharing a word isn't an answer.
        agree = (c.agree_skip and qtype == "yes_no" and len(top) >= 2 and top[0]["has_anchor"]
                 and sum(x["has_anchor"] for x in top[:3]) >= 2)
        clear = top[0]["has_anchor"] and (len(top) == 1 or margin >= c.winner_margin or agree)
        # open questions ("what's your favorite food?"): sharing a word isn't an answer,
        # so the algorithm only answers alone for yes/no questions
        if qtype != "yes_no" and self.llm is not None and c.transport_mode != "algo":
            clear = False
        debug.update(margin=round(margin, 3), agree=agree)
        ai_openers = []
        mode = c.transport_mode if self.llm is not None else "algo"

        route, chosen = None, []
        if not clear and mode != "algo":
            # 6. AI picks numbers (multiple choice), consensus vote
            if c.debug:
                print(f"(close call - asking the AI, {c.votes} votes) ", end="", flush=True)
            max_words = c.write_max_words if mode == "write" else c.opener_max_words
            styles = None if mode == "write" else templates.OPENERS[("FOUND", tone)]
            msgs = build_messages(question, vessels, c.persona_name, c.agent_label,
                                  self.style, max_words, mode == "write", styles)
            result = vote(self.llm, msgs, len(vessels), c.votes, styles)
            debug.update(votes=result["raw"], agreement=result["agreement"], vote_status=result["status"])
            if result["status"] == "error":
                if c.debug:
                    print("(AI didn't answer in time - using the algorithm) ", end="", flush=True)
            elif result["status"] != "ok":
                return self._idk(tone, "idk_votes", debug, bool(exclude))
            else:
                chosen = [vessels[p - 1] for p in result["picks"]]
                ai_openers = result["openers"]
                route = "ai_pick"
                debug["needs_synth"] = result.get("needs_synth", False)

        if route is None:
            # statements before questions ("do asian people eat hot cheetos?" isn't about me)
            anchored = sorted([v for v in vessels if v["has_anchor"]], key=lambda v: v["is_question"])
            if not anchored:
                return self._idk(tone, "idk_gate", debug, bool(exclude))
            chosen = anchored[:2] if agree else anchored[:1]
            if not clear:   # close call without the AI: add the runner-up if it also has the key word
                chosen += [v for v in anchored[1:2] if v["combo"] >= anchored[0]["combo"] - c.winner_margin]
            route = "algo" if debug.get("vote_status") != "error" else "algo_fallback"

        # 7. verdict (rules) -> opener -> render
        changed = False
        if qtype == "yes_no":
            # the verdict sees every packed message about the subject that states a feeling,
            # so a newer "i love it now" can't hide behind a clear winner
            # (top 15, so a "guilty pleasure" message ranked #8 still counts)
            verb = classify.question_verbs(question) or None
            objects = [t for t in content_terms(question) if not verb or t not in {stem(v) for v in verb}]
            # the thing being asked about ("coffee" in "do you hate coffee?")
            # (never the verb itself: "hiked" in "have you hiked in the pasadena mountains?")
            anchor = top[0].get("anchor") if top else None
            subject = [anchor] if anchor and anchor in objects else objects
            # quotes must be about it ("i hate sweet stuff" is not about coffee)
            about = [v for v in chosen if mentions_object(v["text"], subject)]
            chosen = about or [v for v in vessels if v["has_anchor"]][:2]
            if not chosen:
                return self._idk(tone, "idk_gate", debug, bool(exclude))
            chosen_ids = {v["idx"] for v in chosen}
            wide = pack(cands[:15], question, 15)
            def states(v):
                return (polarity(v["text"]) != 0
                        or (verb and mentions_object(v["text"], objects) and action_polarity(v["text"], verb) != 0)
                        or action_polarity(v["text"], HABIT_VERBS) > 0)
            extra = [v for v in wide if v["idx"] not in chosen_ids and v["has_anchor"]
                     and not v["is_question"] and states(v)]
            verdict, changed, ordered = decide(chosen + extra, flip=classify.asks_negative(question),
                                               verb=verb, objects=objects, subject=subject)
            if debug.get("possession") and verdict == "UNCLEAR":
                verdict = "YES"                # "U look like my sister" proves I have one
            debug.update(verb=verb, subject=subject)
            # show the messages that actually support the verdict
            chosen = ordered if (changed or verdict != "UNCLEAR") else chosen
            opener = templates.pick("CHANGED" if changed else verdict, tone)   # verdict is never the AI's call
        else:
            opener = None
            max_words = c.write_max_words if mode == "write" else c.opener_max_words
            evidence = [v["raw"] for v in chosen]
            for o in ai_openers:
                opener = check_opener(o, evidence, question, c.persona_name, max_words)
                if opener:
                    break
            debug["opener_from_ai"] = bool(opener)
            opener = opener or templates.pick("FOUND", tone)
            if qtype == "list":
                chosen = chosen[:3]

        chosen = chosen[:3]

        # 8. LAST RESORT: no single quote answers it -> one checked sentence built from the quotes
        synth = None
        if (qtype != "yes_no" and debug.get("needs_synth") and c.synthesis and self.llm is not None
                and len(chosen) >= 1):
            from transport import synth as S
            shown = [dict(v, num=i + 1) for i, v in enumerate(chosen)]
            try:
                raw = S.synthesize(self.llm, question, shown, c.persona_name, c.agent_label, c.synth_max_words)
            except Exception as e:
                raw = f"error: {e}"
            synth = S.check(raw, shown, question, c.persona_name, c.synth_max_words)
            debug.update(synth_raw=raw, synth_ok=bool(synth))
            if synth:
                route = "ai_synth"
        return self._finish(opener, chosen, qtype, changed, route, debug, synth)

    # ---------- helpers ----------
    @property
    def store(self):
        return self.searcher.store

    def _thread(self, idx):
        if not self.c.threads or not hasattr(self.store, "thread"):
            return []
        return self.store.thread(idx, self.c.thread_window_sec, self.c.thread_max)

    def _context(self, idx) -> str:
        """Neighbor messages as one short line, for the AI picker."""
        lines = [self.store.rows[j]["text"][:60] for j, is_q in self._thread(idx) if not is_q]
        return " / ".join(lines)

    def _finish(self, opener, chosen, qtype, changed, route, debug, synth=None):
        shown = [dict(v, num=i + 1) for i, v in enumerate(chosen)]   # renumber 1..n
        threads = {}
        for v in shown:
            t = self._thread(v["idx"])
            if t:
                threads[v["num"]] = [(v["display"] if is_q else self.store.rows[j]["text"], is_q)
                                     for j, is_q in t]
        text = render(opener, shown, qtype, changed, threads=threads, synth=synth)
        display = render(opener, shown, qtype, changed, highlight=True, threads=threads, synth=synth)
        return TransportResult(text, route, [v["idx"] for v in chosen], debug, display)

    def _compare(self, question, opts, tone, debug):
        """'cheetos or burritos?' -> score each side by how I talk about it."""
        debug["qtype"] = "compare"
        sides = []
        for stem_, word in opts:
            cands = self.searcher.search(f"do you like {word}")
            mine = [x for x in cands if x["first_person"] and not x["is_question"]
                    and stem_ in {s for s in __import__("retrieval.gradient", fromlist=["x"]).content_terms(x["text"])}]
            vs = pack(mine[:8], f"do you like {word}", 8)
            def side_score(v, term=stem_):
                from transport.verdict import polarity_about
                p = polarity_about(v["text"], [term])
                return p if p else max(0, action_polarity(v["text"], HABIT_VERBS))   # "i drink coffee everyday"
            scored = sorted(((side_score(v), v) for v in vs), key=lambda p: -p[0])
            score = sum(p for p, _ in scored)
            best = [v for p, v in scored if p > 0][:3]
            worst = [v for p, v in scored if p < 0][:1]
            sides.append({"word": word, "score": score, "best": best, "worst": worst, "n": len(vs)})
        a, b = sides
        debug["compare"] = {a["word"]: a["score"], b["word"]: b["score"]}
        if not a["best"] and not b["best"] and a["score"] == b["score"]:
            return self._idk(tone, "idk_empty", debug)
        def pick_two(first, second):
            # one quote per side; a message about BOTH ("burritos xxtra hot cheetos...") counts once
            out = first["best"][:1]
            used = {v["idx"] for v in out}
            out += [v for v in second["best"] if v["idx"] not in used][:1]
            return out
        if a["score"] == b["score"] and a["best"] and b["best"]:
            opener = "Honestly I like both." if tone == "neutral" else "Lowkey both tbh."
            chosen = pick_two(a, b)
        else:
            win, lose = (a, b) if a["score"] > b["score"] else (b, a)
            if win["best"]:
                opener = f"{win['word'].capitalize()}, for sure." if tone == "casual" else f"{win['word'].capitalize()}."
            else:                              # winner only by the other side being disliked
                opener = f"{win['word'].capitalize()} I guess, not big on {lose['word']}."
            chosen = pick_two(win, lose) or lose.get("worst", [])
        return self._finish(opener, chosen[:2], "compare", False, "algo", debug)
