#!/usr/bin/env python3
"""
D5 — Build the C2 (NL -> BPMN) dataset through the validation loop.

Implements deliverable D5 of doc/Training-Data-Build-Spec.md (§7.3) with the
dual-representation format (§3.3, TDD §4.5). Each seed record supplies a natural-
language process description plus an intermediate representation (IR). This script:

    IR --ir_to_bpmn--> BPMN 2.0 XML --wellformed--> --SpiffWorkflow XSD schema-->
        --> accept row (store IR + XML) | reject (log reason)

Only rows whose XML passes both checks are written, guaranteeing every C2 row is a
valid, importable diagram. Seed files are JSONL with at least:
    {"instruction": "<NL description>", "ir": { ...IR... }, "meta": { ...optional... }}

Usage:
    python build_c2_dataset.py --seeds data/seeds/c2_seeds_firstparty.jsonl \
        [data/raw/c2_seeds_pet.jsonl] --out data/instruction/instruction_c2.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ir_to_bpmn import build_bpmn, IRError          # noqa: E402
from bpmn_validate import wellformed, schema_valid, spiff_available  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Build validated C2 NL->BPMN rows (D5).")
    ap.add_argument("--seeds", nargs="+", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data/instruction/instruction_c2.jsonl"))
    ap.add_argument("--split", default="train")
    ap.add_argument("--eval", action="store_true",
                    help="Mark rows as a held-out eval set (split=test, is_eval=true, id prefix c2eval).")
    args = ap.parse_args()
    if args.eval:
        args.split = "test"

    if not spiff_available():
        print("WARNING: SpiffWorkflow not installed — XSD schema check will be skipped.\n"
              "         Install it (pip install SpiffWorkflow) for a real validation gate.")

    accepted, rejected = [], []
    idx = 0
    for seed_file in args.seeds:
        if not seed_file.exists():
            print(f"(skip) seed file not found: {seed_file}")
            continue
        for lineno, line in enumerate(seed_file.open(encoding="utf-8"), 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            nl, ir = rec.get("instruction"), rec.get("ir")
            src = (rec.get("meta") or {}).get("source", seed_file.stem)
            if not nl or not ir:
                rejected.append((str(seed_file), lineno, "missing instruction or ir"))
                continue
            try:
                xml = build_bpmn(ir)
            except IRError as e:
                rejected.append((str(seed_file), lineno, f"IR error: {e}"))
                continue
            ok_wf, err_wf = wellformed(xml)
            if not ok_wf:
                rejected.append((str(seed_file), lineno, f"not well-formed: {err_wf}"))
                continue
            ok_sc, err_sc = schema_valid(xml)
            if ok_sc is False:
                rejected.append((str(seed_file), lineno, f"schema invalid: {err_sc}"))
                continue
            idx += 1
            meta = {
                "capability": "C2",
                "ir_format": "json-graph",
                "source": src,
                "xml_validated": True,
                "schema_checked": bool(ok_sc),  # False-y only if SpiffWorkflow absent
                "split": args.split,
                "id": f"{'c2eval' if args.eval else 'c2'}-{idx:04d}",
            }
            if args.eval:
                meta["is_eval"] = True
            accepted.append({"instruction": nl, "input": "", "output_ir": ir, "output": xml, "meta": meta})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in accepted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Accepted (valid) : {len(accepted)} -> {args.out}")
    print(f"Rejected         : {len(rejected)}")
    for sf, ln, why in rejected[:30]:
        print(f"   {sf}:{ln}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
