#!/usr/bin/env python3
"""
D7 — Dataset release gate.

Implements deliverable D7 of doc/Training-Data-Build-Spec.md (§10). A single
pass/fail gate that asserts the dataset is fit to train on. It runs four checks and
exits non-zero if any fails, so it can gate CI / a release:

  1. VALIDATION  — every training & eval file passes validate_rows (0 errors).
  2. COVERAGE    — each in-scope capability meets its §5 SFT target; preference meets target.
  3. EVAL SETS   — a non-empty eval set exists for every in-scope capability.
  4. LEAKAGE     — no eval row duplicates / near-duplicates a training row (§8).

The gate is expected to REPORT-NOT-READY while data is still being scaled (coverage
gaps); that is the honest signal. Structural failures (validation, leakage, missing
eval sets) are the ones that indicate a real defect to fix.

Usage:
    python release_gate.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_rows import validate_file                          # noqa: E402
from coverage_report import analyze, SFT_TARGETS, PREFERENCE_TARGET  # noqa: E402

DATA = Path("data")

# SFT training files that feed coverage (Axis 1).
SFT_TRAIN_FILES = [
    DATA / "instruction/instruction_v2.jsonl",
    DATA / "instruction/instruction_c1_authored.jsonl",
    DATA / "instruction/instruction_c1_kb.jsonl",
    DATA / "instruction/instruction_c2.jsonl",
    DATA / "instruction/instruction_c3.jsonl",
    DATA / "instruction/instruction_c4.jsonl",
    DATA / "instruction/instruction_c6.jsonl",
    DATA / "instruction/instruction_c7.jsonl",
]
PREFERENCE_FILES = [DATA / "preference/preference_v2.jsonl",
                    DATA / "preference/preference_generated.jsonl"]
# Eval sets expected per in-scope capability (C2 eval is a known gap).
EVAL_FILES = {
    "C1": DATA / "eval/eval_c1_qa.jsonl",
    "C2": DATA / "eval/eval_c2_gen.jsonl",
    "C3": DATA / "eval/eval_c3_defects.jsonl",
    "C4": DATA / "eval/eval_c4_narrate.jsonl",
    "C6": DATA / "eval/eval_c6_automation.jsonl",
    "C7": DATA / "eval/eval_c7_compliance.jsonl",
}
IN_SCOPE = ["C1", "C2", "C3", "C4", "C6", "C7"]
LEAK_JACCARD = 0.6


def _toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _rows(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def check_validation():
    files = SFT_TRAIN_FILES + PREFERENCE_FILES + list(EVAL_FILES.values())
    problems = []
    for p in files:
        if not p.exists():
            problems.append(f"{p}: MISSING")
            continue
        rep = validate_file(p)
        if rep["errors"]:
            problems.append(f"{p}: {len(rep['errors'])} error(s) — e.g. {rep['errors'][0]}")
    return (not problems), problems


def check_coverage():
    present = [p for p in SFT_TRAIN_FILES + PREFERENCE_FILES if p.exists()]
    a = analyze(present)
    rows = []
    ok = True
    for cap in IN_SCOPE:
        have = a["sft_meta"].get(cap, 0) + a["sft_heur"].get(cap, 0)
        target = SFT_TARGETS[cap]
        met = have >= target
        ok = ok and met
        rows.append((cap, have, target, met))
    pref_have = a["pref_count"]
    pref_met = pref_have >= PREFERENCE_TARGET
    ok = ok and pref_met
    return ok, rows, (pref_have, PREFERENCE_TARGET, pref_met)


def check_eval_sets():
    problems = []
    for cap in IN_SCOPE:
        p = EVAL_FILES.get(cap)
        if p is None:
            problems.append(f"{cap}: no eval set defined")
        elif not p.exists() or not _rows(p):
            problems.append(f"{cap}: eval set missing/empty ({p})")
    return (not problems), problems


def check_leakage():
    """Flag eval rows that duplicate/near-duplicate a training row (§8)."""
    train_rows = []
    for p in SFT_TRAIN_FILES + PREFERENCE_FILES:
        train_rows += _rows(p)
    train_inputs = {(_norm_input(r)) for r in train_rows if _norm_input(r)}
    train_qtoks = [(_qtext(r), _toks(_qtext(r))) for r in train_rows if _qtext(r)]

    flags = []
    for cap, p in EVAL_FILES.items():
        for r in _rows(p):
            inp = _norm_input(r)
            if inp and inp in train_inputs:
                flags.append(f"{cap} {r.get('meta', {}).get('id', '?')}: exact input also in training set")
                continue
            q = _qtext(r)
            if q and not inp:  # question-only rows (C1): fuzzy check
                qt = _toks(q)
                for tq, tt in train_qtoks:
                    j = len(qt & tt) / len(qt | tt) if qt | tt else 0
                    if j > LEAK_JACCARD:
                        flags.append(f"{cap} {r.get('meta', {}).get('id', '?')}: "
                                     f"question ~{j:.2f} similar to a training question")
                        break
    return (not flags), flags


def _norm_input(r):
    v = r.get("input") or ""
    return re.sub(r"\s+", " ", v).strip()


def _qtext(r):
    return (r.get("instruction") or r.get("prompt") or "").strip()


def main() -> int:
    print("=" * 64)
    print("D7 — DATASET RELEASE GATE")
    print("=" * 64)

    v_ok, v_problems = check_validation()
    print(f"\n[1] VALIDATION : {'PASS' if v_ok else 'FAIL'}")
    for p in v_problems:
        print("      - " + p)

    c_ok, c_rows, (pref_have, pref_target, pref_met) = check_coverage()
    print(f"\n[2] COVERAGE   : {'PASS' if c_ok else 'NOT MET'}")
    print("      cap   have / target")
    for cap, have, target, met in c_rows:
        print(f"      {cap:4s}  {have:4d} / {target:<4d}  {'OK' if met else 'gap ' + str(target - have)}")
    print(f"      pref  {pref_have:4d} / {pref_target:<4d}  {'OK' if pref_met else 'gap ' + str(pref_target - pref_have)}")

    e_ok, e_problems = check_eval_sets()
    print(f"\n[3] EVAL SETS  : {'PASS' if e_ok else 'INCOMPLETE'}")
    for p in e_problems:
        print("      - " + p)

    l_ok, l_flags = check_leakage()
    print(f"\n[4] LEAKAGE    : {'PASS' if l_ok else 'FAIL'}")
    for p in l_flags[:20]:
        print("      - " + p)

    # Structural failures (must-fix) vs coverage (scaling in progress)
    structural_ok = v_ok and e_ok and l_ok
    overall_ok = structural_ok and c_ok
    print("\n" + "-" * 64)
    print(f"STRUCTURAL (validation + eval sets + leakage): {'PASS' if structural_ok else 'FAIL'}")
    print(f"COVERAGE (v1 §5 targets)                     : {'MET' if c_ok else 'NOT MET (scaling in progress)'}")
    print(f"RELEASE GATE                                 : {'READY' if overall_ok else 'NOT READY'}")
    print("-" * 64)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
