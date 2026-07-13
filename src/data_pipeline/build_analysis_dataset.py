#!/usr/bin/env python3
"""
D6 — Build the C4 (narrate), C6 (automation), C7 (compliance) datasets + eval sets.

Implements deliverable D6 of doc/Training-Data-Build-Spec.md (§4, §6). Each of these
capabilities takes a BPMN diagram as input and produces an analysis. Gold outputs are
generated deterministically by analyze_bpmn.py from the actual graph structure, so they
are correct by construction (and, per spec Principle 4, should be human-reviewed before
production training — meta.source records that they are analyzer-generated).

To avoid train/eval leakage (spec §8), the two input pools are disjoint:
  - TRAIN inputs : our validated C2 diagrams (data/instruction/instruction_c2.jsonl `output`)
  - EVAL inputs  : the MIWG reference diagrams (data/raw/bpmn-miwg-test-suite/Reference)

Writes six files: instruction_c4/c6/c7.jsonl (train) and eval_c4_narrate/
eval_c6_automation/eval_c7_compliance.jsonl (test).

Usage:
    python build_analysis_dataset.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_bpmn import (parse, narrate, automation_opportunities, automation_to_text,  # noqa: E402
                          compliance_check, compliance_to_text)
from diagram_pools import miwg_reference_split, hdbpmn_deduped  # noqa: E402

C4_INSTR = ("Explain this BPMN 2.0 diagram in plain English, describing the flow from "
            "start to end so a non-technical reader can follow it.")
C6_INSTR = ("Analyse this BPMN 2.0 diagram and identify opportunities to automate steps. "
            "For each, name the element and explain why it is a candidate.")
C7_INSTR = ("Check this BPMN 2.0 process against the governance rule set and report which "
            "rules are satisfied and which are gaps, with recommendations.")


def load_c2_diagrams(path: Path):
    out = []
    if not path.exists():
        return out
    for line in path.open(encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            out.append((r["meta"].get("id", "c2"), r["output"], "c2-generated"))
    return out




def make_rows(diagrams, ruleset, split, is_eval):
    c4, c6, c7 = [], [], []
    for i, (name, xml, source) in enumerate(diagrams, 1):
        try:
            m = parse(xml)
        except Exception:
            continue
        base_meta = {"source": f"analyzer-generated ({source})", "source_diagram": name,
                     "split": split, "review_status": "auto-generated (needs human review)"}
        if is_eval:
            base_meta["is_eval"] = True

        c4.append({"instruction": C4_INSTR, "input": xml, "output": narrate(m),
                   "meta": {**base_meta, "capability": "C4", "id": f"c4{'eval' if is_eval else ''}-{i:04d}"}})

        findings = automation_opportunities(m)
        c6.append({"instruction": C6_INSTR, "input": xml, "output": automation_to_text(findings),
                   "meta": {**base_meta, "capability": "C6", "n_opportunities": len(findings),
                            "id": f"c6{'eval' if is_eval else ''}-{i:04d}"}})

        report = compliance_check(m, ruleset)
        c7.append({"instruction": C7_INSTR, "input": xml, "output": compliance_to_text(report),
                   "meta": {**base_meta, "capability": "C7", "ruleset": report["ruleset"],
                            "passed": report["passed"], "total": report["total"],
                            "results": report["results"], "id": f"c7{'eval' if is_eval else ''}-{i:04d}"}})
    return c4, c6, c7


def write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build C4/C6/C7 datasets + eval sets (D6).")
    ap.add_argument("--c2", type=Path, default=Path("data/instruction/instruction_c2.jsonl"))
    ap.add_argument("--miwg", type=Path, default=Path("data/raw/bpmn-miwg-test-suite/Reference"))
    ap.add_argument("--hdbpmn", type=Path, default=Path("data/raw/hdBPMN"))
    ap.add_argument("--rules", type=Path, default=Path("data/seeds/compliance_rules.json"))
    args = ap.parse_args()

    ruleset = json.loads(args.rules.read_text(encoding="utf-8"))
    # Disjoint MIWG split so the rich real-world elements (boundary events, pools/lanes,
    # data, message flows, multi-instance) appear in BOTH train and eval — fixing the
    # train/eval mismatch found in the BPMN-expert audit.
    miwg_train, miwg_eval = miwg_reference_split(args.miwg)
    miwg_train = [(n, x, "miwg-reference (CC BY 3.0)") for n, x in miwg_train]
    miwg_eval = [(n, x, "miwg-reference (CC BY 3.0)") for n, x in miwg_eval]
    hdbpmn = [(n, x, "hdbpmn (CC BY 4.0)") for n, x in hdbpmn_deduped(args.hdbpmn)]

    train_diagrams = load_c2_diagrams(args.c2) + miwg_train
    eval_diagrams = miwg_eval + hdbpmn
    print(f"Train inputs        : C2 {len(train_diagrams) - len(miwg_train)} + MIWG-train {len(miwg_train)} = {len(train_diagrams)}")
    print(f"Eval inputs         : MIWG-eval {len(miwg_eval)} + hdBPMN {len(hdbpmn)} = {len(eval_diagrams)}")
    print(f"Compliance ruleset  : {ruleset.get('ruleset')} ({len(ruleset.get('rules', []))} rules)")

    tr4, tr6, tr7 = make_rows(train_diagrams, ruleset, "train", is_eval=False)
    ev4, ev6, ev7 = make_rows(eval_diagrams, ruleset, "test", is_eval=True)

    counts = {
        "data/instruction/instruction_c4.jsonl": write(Path("data/instruction/instruction_c4.jsonl"), tr4),
        "data/instruction/instruction_c6.jsonl": write(Path("data/instruction/instruction_c6.jsonl"), tr6),
        "data/instruction/instruction_c7.jsonl": write(Path("data/instruction/instruction_c7.jsonl"), tr7),
        "data/eval/eval_c4_narrate.jsonl": write(Path("data/eval/eval_c4_narrate.jsonl"), ev4),
        "data/eval/eval_c6_automation.jsonl": write(Path("data/eval/eval_c6_automation.jsonl"), ev6),
        "data/eval/eval_c7_compliance.jsonl": write(Path("data/eval/eval_c7_compliance.jsonl"), ev7),
    }
    print("\nWritten:")
    for f, c in counts.items():
        print(f"   {c:4d}  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
