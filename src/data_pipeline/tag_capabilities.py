#!/usr/bin/env python3
"""
D4 (part 1) — Tag legacy rows with meta.capability + meta.id.

Implements the tagging half of deliverable D4 in doc/Training-Data-Build-Spec.md.
The POC datasets predate the capability model, so Axis 1 of the coverage report
(coverage_report.py) can only *estimate* their capability. This script assigns an
authoritative meta.capability + stable meta.id to every row using transparent,
deterministic rules, and writes the tagged v2 files under the spec §9 layout.

Rules (applied to the instruction / prompt text):
  - C2 (generation) : matches "write|show ... BPMN 2.0 XML"  (asks to author a diagram)
  - C3 (review)     : contains "what is wrong" / "what's wrong"  (critique a design)
  - C1 (Q&A/tutor)  : everything else (conceptual questions)  [default]

Borderline critique-of-a-statement questions intentionally fall through to C1; the
rules favour precision on C2/C3 over catching every edge case. Re-tag by editing
these rules and re-running — the script is deterministic and idempotent.

Usage:
    python tag_capabilities.py --in data/bpmn_instruction_dataset.jsonl \
        --out data/instruction/instruction_v2.jsonl --type sft
    python tag_capabilities.py --in data/bpmn_dpo_dataset.jsonl \
        --out data/preference/preference_v2.jsonl --type preference
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

RE_C2 = re.compile(r"\b(write|show)\b.*\bbpmn\s*2\.0\s*xml\b", re.IGNORECASE)
RE_C3 = re.compile(r"what'?s?\s+is\s+wrong|what'?s\s+wrong", re.IGNORECASE)


def classify(row: dict) -> str:
    text = (row.get("instruction") or row.get("prompt") or "")
    if RE_C2.search(text):
        return "C2"
    if RE_C3.search(text):
        return "C3"
    return "C1"


def main() -> int:
    ap = argparse.ArgumentParser(description="Tag legacy rows with meta.capability (D4).")
    ap.add_argument("--in", dest="infile", type=Path, required=True)
    ap.add_argument("--out", dest="outfile", type=Path, required=True)
    ap.add_argument("--type", choices=["sft", "preference"], required=True)
    args = ap.parse_args()

    if not args.infile.exists():
        print(f"ERROR: input not found: {args.infile}")
        return 2

    prefix = "sft" if args.type == "sft" else "pref"
    dist = Counter()
    out_rows = []
    with args.infile.open(encoding="utf-8") as f:
        idx = 0
        for line in f:
            if not line.strip():
                continue
            idx += 1
            row = json.loads(line)
            cap = classify(row)
            dist[cap] += 1
            meta = dict(row.get("meta") or {})
            meta.setdefault("capability", cap)
            # Always (re)assert an authoritative capability from the rule:
            meta["capability"] = cap
            meta.setdefault("source", "poc-legacy")
            meta.setdefault("split", "train")
            meta["id"] = f"{prefix}-{idx:04d}"
            row["meta"] = meta
            out_rows.append(row)

    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    with args.outfile.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Input           : {args.infile}")
    print(f"Output          : {args.outfile}")
    print(f"Rows tagged     : {len(out_rows)}")
    print("Capability dist :", dict(dist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
