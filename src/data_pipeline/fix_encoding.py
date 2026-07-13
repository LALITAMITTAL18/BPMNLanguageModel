#!/usr/bin/env python3
"""
D1 — UTF-8 / mojibake repair for BPMN datasets.

Implements deliverable D1 of doc/Training-Data-Build-Spec.md (§3.4).

Some POC datasets (notably data/bpmn_dpo_dataset.jsonl) were saved through a bad
encoding round-trip: UTF-8 bytes were decoded as CP-1252, so characters like the
em-dash (U+2014, bytes E2 80 94) became the three-character sequence "â€”"
(U+00E2 U+20AC U+201D). This script reverses that corruption.

Reversal: for any string containing a mojibake marker, re-encode it as CP-1252 to
recover the original UTF-8 bytes, then decode those bytes as UTF-8. Only applied
when it succeeds and removes markers, so it is safe and idempotent.

Usage:
    python fix_encoding.py <file.jsonl> [--check]

    (no flag)  repair the file in place (writes clean UTF-8, no \\u escapes)
    --check    dry run: report how many strings would change, write nothing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Lone marker characters that essentially never appear in legitimate English BPMN
# text but are the tell-tale first byte of CP-1252-over-UTF-8 mojibake sequences
# (e.g. "â€”" em-dash, "â†'" arrow, "Â " nbsp, "Ã©" é).
MOJIBAKE_MARKERS = ("â", "Â", "Ã")

try:
    import ftfy  # purpose-built, well-tested fixer; preferred when available
    _HAVE_FTFY = True
except Exception:  # pragma: no cover
    _HAVE_FTFY = False


def looks_mojibaked(s: str) -> bool:
    return any(m in s for m in MOJIBAKE_MARKERS)


def repair_string(s: str) -> str:
    """Reverse CP-1252-over-UTF-8 mojibake. Returns original string if not applicable.

    Uses ftfy when installed (handles mixed real-unicode + mojibake surgically).
    Falls back to a whole-string CP-1252 round-trip, guarded so it only applies
    when it removes markers without raising.
    """
    if not looks_mojibaked(s):
        return s
    if _HAVE_FTFY:
        fixed = ftfy.fix_text(s)
        return fixed
    try:
        candidate = s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
    # Accept only if it did not leave the string looking equally/more mojibaked.
    if looks_mojibaked(candidate) and _marker_count(candidate) >= _marker_count(s):
        return s
    return candidate


def _marker_count(s: str) -> int:
    return sum(s.count(m) for m in MOJIBAKE_MARKERS)


def repair_obj(obj, counter: dict):
    """Recursively repair all string values in a JSON-like object."""
    if isinstance(obj, str):
        fixed = repair_string(obj)
        if fixed != obj:
            counter["strings"] += 1
        return fixed
    if isinstance(obj, list):
        return [repair_obj(x, counter) for x in obj]
    if isinstance(obj, dict):
        return {k: repair_obj(v, counter) for k, v in obj.items()}
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair mojibake in a JSONL dataset (D1).")
    ap.add_argument("file", type=Path, help="Path to the .jsonl file")
    ap.add_argument("--check", action="store_true", help="Dry run; report only, write nothing")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        return 2

    counter = {"strings": 0}
    rows_changed = 0
    out_lines = []
    with args.file.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                out_lines.append(line)
                continue
            row = json.loads(line)
            before = json.dumps(row, ensure_ascii=False, sort_keys=True)
            fixed = repair_obj(row, counter)
            after = json.dumps(fixed, ensure_ascii=False, sort_keys=True)
            if before != after:
                rows_changed += 1
            out_lines.append(json.dumps(fixed, ensure_ascii=False))

    print(f"File            : {args.file}")
    print(f"Strings repaired: {counter['strings']}")
    print(f"Rows changed    : {rows_changed}")

    if args.check:
        print("Mode            : --check (dry run, nothing written)")
        return 0

    if rows_changed == 0:
        print("Mode            : in-place (no changes needed, file left untouched)")
        return 0

    args.file.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print("Mode            : in-place (file rewritten as clean UTF-8)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
