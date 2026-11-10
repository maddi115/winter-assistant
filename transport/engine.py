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
from transport.verdict import decide, polarity


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
        tone = classify.tone(tone_source or question)
        qtype = classify.question_type(question)
        debug = {"qtype": qtype, "tone": tone}

        # 2. search
        cands = self.searcher.search(question, exclude)
        if exclude:   # follow-up: only messages that still share the question's words
            cands = [x for x in cands if x["has_anchor"]]
        # only things I said ABOUT MYSELF can answer a question about me:
        # first person ("I", "my", "we") and not a question I asked someone else
        cands = [x for x in cands if x["first_person"] and not x["is_question"]]
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

        # 4. pack
        vessels = pack(top, question, c.vessels_k)

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
            print(f"(close call - asking the AI, {c.votes} votes) ", end="", flush=True)
            max_words = c.write_max_words if mode == "write" else c.opener_max_words
            styles = None if mode == "write" else templates.OPENERS[("FOUND", tone)]
            msgs = build_messages(question, vessels, c.persona_name, c.agent_label,
                                  self.style, max_words, mode == "write", styles)
            result = vote(self.llm, msgs, len(vessels), c.votes, styles)
            debug.update(votes=result["raw"], agreement=result["agreement"], vote_status=result["status"])
            if result["status"] == "error":
                print("(AI didn't answer in time - using the algorithm) ", end="", flush=True)
            elif result["status"] != "ok":
                return self._idk(tone, "idk_votes", debug, bool(exclude))
            else:
                chosen = [vessels[p - 1] for p in result["picks"]]
                ai_openers = result["openers"]
                route = "ai_pick"

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
            extra = [v for v in vessels if v not in chosen and v["has_anchor"]
                     and not v["is_question"] and polarity(v["text"]) != 0]
            verdict, changed, ordered = decide(chosen + extra, flip=classify.asks_negative(question))
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
        shown = [dict(v, num=i + 1) for i, v in enumerate(chosen)]   # renumber 1..n
        text = render(opener, shown, qtype, changed)
        display = render(opener, shown, qtype, changed, highlight=True)
        return TransportResult(text, route, [v["idx"] for v in chosen], debug, display)
