# src/data_pipeline

Scripts that implement the data deliverables of
[`doc/Training-Data-Build-Spec.md`](../../doc/Training-Data-Build-Spec.md).
Governed by [`CLAUDE.md`](../../CLAUDE.md): all work traces to a capability (C#)/requirement (FR-#).

## Scripts

| Script | Deliverable | What it does |
|--------|-------------|--------------|
| `fix_encoding.py` | **D1** | Repairs CP-1252-over-UTF-8 mojibake (e.g. `â€"` → `—`, `â†'` → `→`) in a JSONL dataset. Uses `ftfy` when installed, else a guarded CP-1252 round-trip. Idempotent. |
| `validate_rows.py` | **D2** | Acceptance gate: valid JSON, required fields per row type, no mojibake, no duplicate `meta.id`, embedded XML well-formedness. Non-zero exit on error → usable in CI. |
| `coverage_report.py` | **D2** | Coverage baseline on two axes (capability × volume; BPMN element/type). Reads `meta.capability` when present; heuristic estimate for untagged legacy rows. |

## Usage

```bash
# D1 — repair encoding (dry run first, then apply in place)
python src/data_pipeline/fix_encoding.py data/bpmn_dpo_dataset.jsonl --check
python src/data_pipeline/fix_encoding.py data/bpmn_dpo_dataset.jsonl

# D2 — validate a dataset (exit code != 0 on errors)
python src/data_pipeline/validate_rows.py data/bpmn_instruction_dataset.jsonl [--strict]

# D2 — coverage report (prints + optional markdown artifact)
python src/data_pipeline/coverage_report.py data/*.jsonl --md doc/reports/dataset-coverage-baseline.md
```

## Dependencies

- **Core checks: standard library only** — the scripts run with no third-party packages.
- **`ftfy`** (recommended, in `requirements.txt`) — best-quality mojibake repair for `fix_encoding.py`.
- **Optional / future (deep validation in `validate_rows.py`):**
  - `SpiffWorkflow` (pip) — BPMN 2.0 schema validation, and
  - `bpmnlint` (npm) — configurable rule linting.
  These activate for **C2 generation rows** and are **not yet exercised** because the current
  data contains no complete C2 diagrams (only tutoring snippets). Wire them in when C2 rows
  exist (deliverable D5). See TDD §4.

## Notes

- `validate_rows.py` treats embedded XML in **non-C2** rows as *illustrative fragments*
  (opening-tag-only, `...` placeholders) → warnings, not errors. Full well-formedness/schema
  validity is required only for `meta.capability == "C2"` rows.
- Legacy rows lack `meta.capability`; the many "missing meta.capability" warnings are expected
  until rows are tagged (D4–D6).
