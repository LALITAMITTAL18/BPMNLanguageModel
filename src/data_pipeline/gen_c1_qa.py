#!/usr/bin/env python3
"""
Generate grounded C1 (Q&A/tutor) rows from the curated BPMN knowledge base.

Conceptual Q&A cannot be responsibly bulk-synthesised on-prem (no teacher LLM), so
this generator scales C1 the safe way: the FACTS come from an authored, accurate
knowledge base (data/seeds/bpmn_kb.json), and only the QUESTION FRAMING varies
(definition / notation / when-to-use / contrast), with template rotation to avoid
uniform phrasing. Generated questions are de-duplicated against the existing C1
questions (legacy + authored + eval) so nothing leaks into or duplicates those sets.

Rows are tagged source "first-party-kb-generated" and review_status "needs human
review" (Training-Data-Build-Spec Principle 4).

Usage:
    python gen_c1_qa.py --kb data/seeds/bpmn_kb.json --out data/instruction/instruction_c1_kb.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEF_Q = ["What is a {t} in BPMN 2.0?", "In BPMN 2.0, what is a {t}?",
         "Explain what a {t} is in BPMN 2.0."]
NOT_Q = ["How is a {t} represented in a BPMN 2.0 diagram?",
         "What does a {t} look like in BPMN 2.0?",
         "What is the notation for a {t} in BPMN 2.0?"]
USE_Q = ["When should you use a {t} in BPMN 2.0?",
         "In what situation is a {t} used in BPMN 2.0?"]
CON_Q = ["What is the difference between a {t} and a {c} in BPMN 2.0?",
         "How does a {t} differ from a {c} in BPMN 2.0?"]

# EVAL questions must not leak into training: use the gate's 0.6 threshold against them.
EVAL_C1 = [Path("data/eval/eval_c1_qa.jsonl")]
# Against other TRAINING questions we only drop near-identical duplicates (short templated
# questions legitimately share boilerplate like "what is a ... in BPMN 2.0").
TRAIN_C1 = [Path("data/instruction/instruction_v2.jsonl"),
            Path("data/instruction/instruction_c1_authored.jsonl")]
EVAL_JACCARD = 0.6     # matches release_gate leakage threshold
TRAIN_JACCARD = 0.85   # only true duplicates


def _toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _load_questions(paths):
    qs = []
    for p in paths:
        if not p.exists():
            continue
        for line in p.open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if (r.get("meta") or {}).get("capability", "C1") == "C1":
                    q = r.get("instruction") or r.get("prompt")
                    if q:
                        qs.append(_toks(q))
    return qs


def _max_jaccard(qt, others):
    best = 0.0
    for tt in others:
        if qt | tt:
            best = max(best, len(qt & tt) / len(qt | tt))
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate grounded C1 Q&A from the KB.")
    ap.add_argument("--kb", type=Path, default=Path("data/seeds/bpmn_kb.json"))
    ap.add_argument("--out", type=Path, default=Path("data/instruction/instruction_c1_kb.jsonl"))
    args = ap.parse_args()

    if not args.kb.exists():
        print(f"ERROR: KB not found: {args.kb}", file=sys.stderr)
        return 2

    kb = json.loads(args.kb.read_text(encoding="utf-8"))
    eval_qs = _load_questions(EVAL_C1)
    train_qs = _load_questions(TRAIN_C1)
    within = []  # token sets of questions accepted this run (avoid intra-run near-dupes)
    rows = []
    n = 0
    skipped = 0

    for ci, c in enumerate(kb["concepts"]):
        term = c["term"]
        area = c.get("spec_area", "")
        candidates = []
        # definition
        candidates.append((DEF_Q[ci % len(DEF_Q)].format(t=term), c["definition"]))
        # notation
        if c.get("notation"):
            candidates.append((NOT_Q[ci % len(NOT_Q)].format(t=term),
                               f"A {term} is drawn as {c['notation']}"))
        # when to use
        if c.get("when_to_use"):
            candidates.append((USE_Q[ci % len(USE_Q)].format(t=term),
                               f"Use a {term} {c['when_to_use']}"))
        # contrast
        if c.get("contrast"):
            con = c["contrast"]
            candidates.append((CON_Q[ci % len(CON_Q)].format(t=term, c=con["term"]),
                               f"{c['definition']} In contrast to a {con['term']}: {con['how']}"))

        for q, a in candidates:
            qt = _toks(q)
            # hard-block anything close to an eval question (prevents gate leakage flags);
            # only drop near-identical duplicates against other training questions.
            if _max_jaccard(qt, eval_qs) > EVAL_JACCARD or _max_jaccard(qt, train_qs + within) > TRAIN_JACCARD:
                skipped += 1
                continue
            within.append(qt)
            n += 1
            rows.append({
                "instruction": q, "input": "", "output": a,
                "meta": {"capability": "C1", "source": "first-party-kb-generated",
                         "spec_ref": f"BPMN 2.0 — {area}", "split": "train",
                         "review_status": "auto-generated (needs human review)",
                         "id": f"kbc1-{n:04d}"},
            })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"KB concepts     : {len(kb['concepts'])}")
    print(f"C1 rows written : {len(rows)} -> {args.out}")
    print(f"Skipped (dupes) : {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
