#!/usr/bin/env python3
"""
Training-data preparation (Phase C/D input builder).

Converts the capability datasets into the two formats the trainers consume:

  SFT  (train_sft.py)  <- data/instruction/*.jsonl
       -> chat format: {"messages": [system, user, assistant]}
  DPO  (train_dpo.py)  <- data/preference/*.jsonl
       -> preference format: {"prompt", "chosen", "rejected"}

Deterministic shuffle + a held-out validation split (never trained on). CPU-only —
safe to run anywhere. Outputs to data/training/.

Usage:
    python src/training/prepare_data.py [--val-frac 0.05]
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SYSTEM_PROMPT = (
    "You are a BPMN 2.0 expert assistant. Answer precisely and follow BPMN 2.0 conventions. "
    "When asked to generate a diagram, output valid BPMN 2.0 XML. When asked to review a "
    "diagram, identify concrete issues and how to fix them."
)
INSTRUCTION_DIR = Path("data/instruction")
PREFERENCE_DIR = Path("data/preference")
OUT_DIR = Path("data/training")
SEED = 42


def _read_jsonl(path: Path):
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def _user_content(row):
    instr = row.get("instruction", "")
    inp = row.get("input", "")
    return f"{instr}\n\n{inp}" if isinstance(inp, str) and inp.strip() else instr


def build_sft():
    rows = []
    for p in sorted(INSTRUCTION_DIR.glob("*.jsonl")):
        for r in _read_jsonl(p):
            out = r.get("output")
            if not out:
                continue
            rows.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _user_content(r)},
                    {"role": "assistant", "content": out},
                ],
                "capability": (r.get("meta") or {}).get("capability", "?"),
            })
    return rows


def build_dpo():
    rows = []
    for p in sorted(PREFERENCE_DIR.glob("*.jsonl")):
        for r in _read_jsonl(p):
            if all(k in r for k in ("prompt", "chosen", "rejected")):
                rows.append({"prompt": r["prompt"], "chosen": r["chosen"], "rejected": r["rejected"],
                             "capability": (r.get("meta") or {}).get("capability", "?")})
    return rows


def split(rows, val_frac):
    rng = random.Random(SEED)
    rng.shuffle(rows)
    n_val = max(1, int(len(rows) * val_frac)) if rows else 0
    return rows[n_val:], rows[:n_val]


def _dist(rows):
    from collections import Counter
    return dict(Counter(r.get("capability", "?") for r in rows))


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare SFT + DPO training files.")
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    sft = build_sft()
    dpo = build_dpo()
    sft_tr, sft_val = split(sft, args.val_frac)
    dpo_tr, dpo_val = split(dpo, args.val_frac)

    n1 = _write_jsonl(args.out / "sft_train.jsonl", sft_tr)
    n2 = _write_jsonl(args.out / "sft_val.jsonl", sft_val)
    n3 = _write_jsonl(args.out / "dpo_train.jsonl", dpo_tr)
    n4 = _write_jsonl(args.out / "dpo_val.jsonl", dpo_val)

    print(f"SFT : {n1} train + {n2} val  -> {args.out}/sft_*.jsonl")
    print(f"      capability mix (train): {_dist(sft_tr)}")
    print(f"DPO : {n3} train + {n4} val  -> {args.out}/dpo_*.jsonl")
    print(f"      capability mix (train): {_dist(dpo_tr)}")
    print("\nNote: sft_val / dpo_val are held out from training. The frozen per-capability")
    print("EVAL sets in data/eval/ remain separate and are scored by src/eval/run_eval.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
