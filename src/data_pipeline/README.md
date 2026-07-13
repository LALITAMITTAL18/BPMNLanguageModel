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
| `inject_defects.py` | **D3** | Injects a catalogue of known structural defects into valid BPMN (MIWG reference models) with ground-truth labels → the C3 seeded-defect eval set. Requires `lxml`. |
| `tag_capabilities.py` | **D4** | Assigns authoritative `meta.capability` + stable `meta.id` to legacy rows via transparent rules; writes tagged v2 files. |
| `ir_to_bpmn.py` | **D5** | Deterministic Intermediate-Representation (JSON node/edge graph) → valid BPMN 2.0 XML builder, with a simple DI layout (TDD §4.5). Requires `lxml`. |
| `bpmn_validate.py` | **D5** | Shared validation helpers: `wellformed()` (lxml) and `schema_valid()` (SpiffWorkflow BPMN 2.0 XSD). Used by the C2 builder and by `validate_rows.py`. |
| `build_c2_dataset.py` | **D5** | Builds C2 (NL→BPMN) rows from NL+IR seeds through the validation loop (IR→XML→well-formed→XSD); only passing rows are written, in dual-representation format. |
| `pet_to_ir.py` | **D5** | Conservative PET→IR bootstrap: converts gateway-free, linear PET docs into C2 seeds (validation-gated downstream). Requires `pyarrow`. |
| `analyze_bpmn.py` | **D6** | Deterministic BPMN analyzers used as gold-output generators (and inference-time tools): `narrate` (C4), `automation_opportunities` (C6), `compliance_check` against a configurable rule set (C7). Namespace-agnostic. Requires `lxml`. |
| `build_analysis_dataset.py` | **D6** | Runs the analyzers over C2 diagrams (train) and MIWG diagrams (eval, disjoint inputs → no leakage) to emit the C4/C6/C7 train + eval sets. Compliance rules load from `data/seeds/compliance_rules.json`. |
| `release_gate.py` | **D7** | Single pass/fail release gate: validates every dataset, checks per-capability coverage vs §5 targets, asserts an eval set exists per capability, and checks train/eval leakage. Exits non-zero until ready. |
| `gen_processes.py` | scale | Parametric, diversity-controlled generator (domains × structural patterns × NL templates) → C2 seeds, fed through the validation gate. The main volume lever. |
| `build_preference_dataset.py` | scale | Validation-backed DPO pairs: C2 valid-vs-structurally-broken, C3 correct-finding-vs-missed. |
| `gen_c1_qa.py` | scale | Generates grounded C1 Q&A from the authored KB (`data/seeds/bpmn_kb.json`), varying question framing and de-duplicating against eval (0.6) and other training questions (0.85). |
| `diagram_pools.py` | coverage | Disjoint MIWG train/eval split (+ hdBPMN eval) so rich real-world elements (boundary events, pools/lanes/collaboration, data, message flows) appear in BOTH train and eval — fixes the train/eval element mismatch. |

**Element coverage:** the generator (`gen_processes.py`) and builder (`ir_to_bpmn.py`) now instantiate boundary events, collaborations (pools/lanes/message flows), data objects, multi-instance/loop, script/complex/manual/call/receive/send tasks, throwing events, text annotations, and groups. `inject_defects.py` covers 11 anti-patterns (incl. deadlock, lack-of-synchronization, connectivity violations from soundness/7PMG taxonomies). Only `dataStore` is not generated (SpiffWorkflow rejects unimplemented data stores) — it is present in the MIWG eval set and the C1 knowledge base.

**Scaling regeneration order** (after editing seeds/KB): `gen_processes.py` → `build_c2_dataset.py` → `inject_defects.py --from-jsonl … --cap-per-type 25` → `build_analysis_dataset.py` → `build_preference_dataset.py` → `gen_c1_qa.py` → `release_gate.py`.

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
