#!/usr/bin/env python3
"""
Build validation-backed preference (DPO) pairs to scale the preference set.

Preference data teaches the model to prefer a good response over a plausible-but-worse
one. Rather than hand-authoring, we construct pairs whose 'chosen' is correct BY
CONSTRUCTION and 'rejected' is a concrete, realistic failure mode:

  C2 (generation): prompt = NL description; chosen = the valid, complete BPMN XML;
                   rejected = the same diagram with a structural defect injected
                   (e.g. missing end event / disconnected task). Teaches "prefer a
                   complete, sound diagram over a broken one."
  C3 (review):     prompt = review instruction + a defective diagram; chosen = the
                   correct finding; rejected = "No issues found" (a miss). Teaches
                   "prefer detecting the real defect over overlooking it."

These complement the hand-authored preference_v2.jsonl (kept separate for provenance).

Usage:
    python build_preference_dataset.py [--cap-c2 130 --cap-c3 130]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inject_defects as idf  # noqa: E402

CLEAN_MISS = ("No structural issues found. The process appears well-formed and complete.")


def broken_variant(xml: str):
    """Return a schema-valid-but-structurally-worse variant of a valid diagram, or None."""
    try:
        root = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError:
        return None
    ns = idf.model_ns(root)
    for inj in (idf.inject_missing_end_event, idf.inject_disconnected_element,
                idf.inject_unlabeled_task):
        r = copy.deepcopy(root)
        if inj(r, ns) is not None:
            return idf.serialize(r)
    return None


def _rows(path: Path):
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()] if path.exists() else []


def main() -> int:
    ap = argparse.ArgumentParser(description="Build validation-backed preference pairs.")
    ap.add_argument("--c2", type=Path, default=Path("data/instruction/instruction_c2.jsonl"))
    ap.add_argument("--c3", type=Path, default=Path("data/instruction/instruction_c3.jsonl"))
    ap.add_argument("--out", type=Path, default=Path("data/preference/preference_generated.jsonl"))
    ap.add_argument("--cap-c2", type=int, default=130)
    ap.add_argument("--cap-c3", type=int, default=130)
    args = ap.parse_args()

    pairs = []
    n = 0

    # C2: valid vs structurally-broken
    c2 = _rows(args.c2)
    step = max(1, len(c2) // args.cap_c2)
    for r in c2[::step][:args.cap_c2]:
        rej = broken_variant(r["output"])
        if not rej or rej == r["output"]:
            continue
        n += 1
        pairs.append({"prompt": r["instruction"], "chosen": r["output"], "rejected": rej,
                      "meta": {"capability": "C2", "source": "generated-preference",
                               "rejected_kind": "structural-defect", "split": "train",
                               "id": f"prefgen-{n:04d}"}})

    # C3: correct finding vs missed
    c3_defective = [r for r in _rows(args.c3) if r["meta"].get("defect_type") not in (None, "none")]
    step = max(1, len(c3_defective) // args.cap_c3)
    for r in c3_defective[::step][:args.cap_c3]:
        n += 1
        prompt = r["instruction"] + "\n\n" + r["input"]
        pairs.append({"prompt": prompt, "chosen": r["output"], "rejected": CLEAN_MISS,
                      "meta": {"capability": "C3", "source": "generated-preference",
                               "defect_type": r["meta"].get("defect_type"),
                               "rejected_kind": "missed-defect", "split": "train",
                               "id": f"prefgen-{n:04d}"}})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    from collections import Counter
    dist = Counter(p["meta"]["capability"] for p in pairs)
    print(f"Preference pairs written: {len(pairs)} -> {args.out}")
    print("By capability           :", dict(dist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
