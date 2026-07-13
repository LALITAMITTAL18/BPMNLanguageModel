#!/usr/bin/env python3
"""
Shared diagram pools for training/eval, with a disjoint MIWG split.

The BPMN-expert audit found that the model's TRAINING diagrams (C2-generated) lacked
the "advanced but common" tier — boundary events, pools/lanes/collaboration, data
objects, message flows, multi-instance — which appeared only in the MIWG EVAL set
(a train/eval mismatch). The MIWG reference models (CC BY 3.0) DO contain those
elements, so this module splits them by case-id into disjoint train/eval pools and
lets both the analysis-dataset builder and the defect injector draw rich, real,
license-clean diagrams for TRAINING as well as eval.

Split is deterministic (by sorted index) so runs are reproducible and a given case
never appears in both train and eval (no leakage).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bpmn_validate import schema_valid  # noqa: E402

ATTRIBUTION_MIWG = "BPMN MIWG Test Suite, CC BY 3.0 (https://github.com/bpmn-miwg/bpmn-miwg-test-suite)"


def miwg_reference_split(ref_dir: Path, eval_every: int = 3):
    """Return (train, eval) lists of (name, xml) from XSD-valid MIWG reference models.

    eval_every=3 => every 3rd case (sorted) goes to eval, the rest to train; this
    spreads the rich B/C-series cases across both pools while keeping them disjoint.
    """
    train, evalset = [], []
    if not ref_dir.is_dir():
        return train, evalset
    files = sorted(ref_dir.glob("*.bpmn"))
    idx = 0
    for p in files:
        xml = p.read_text(encoding="utf-8", errors="replace")
        ok, _ = schema_valid(xml)
        if not ok:
            continue
        (evalset if idx % eval_every == 0 else train).append((p.stem, xml))
        idx += 1
    return train, evalset


def hdbpmn_deduped(root_dir: Path):
    """One XSD-valid diagram per hdBPMN exercise (CC BY 4.0) — real-world eval slice."""
    import re
    out, seen = [], set()
    if not root_dir.is_dir():
        return out
    for p in sorted(root_dir.glob("**/*.bpmn")):
        m = re.match(r"(ex\d+)", p.name)
        ex = m.group(1) if m else p.stem
        if ex in seen:
            continue
        xml = p.read_text(encoding="utf-8", errors="replace")
        ok, _ = schema_valid(xml)
        if ok:
            seen.add(ex)
            out.append((f"hdbpmn-{ex}", xml))
    return out


if __name__ == "__main__":
    tr, ev = miwg_reference_split(Path("data/raw/bpmn-miwg-test-suite/Reference"))
    print(f"MIWG reference split: train={len(tr)} eval={len(ev)} (cases: "
          f"{[n for n, _ in tr]} | {[n for n, _ in ev]})")
    print(f"hdBPMN deduped: {len(hdbpmn_deduped(Path('data/raw/hdBPMN')))}")
