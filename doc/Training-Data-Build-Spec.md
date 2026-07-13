# Training-Data Build Spec — BPMN Intelligence Assistant

| | |
|---|---|
| **Document** | Training-Data Build Spec (Spike S-Data, per TDD §8 & §11) |
| **Version** | 0.1 (Draft) |
| **Date** | 2026-07-10 |
| **Governs** | *How* we build and grow the datasets that train & evaluate the model |
| **Constrained by** | [FDD](Functional-Design-Document.md) (frozen), [TDD](Technical-Design-Document.md), [CLAUDE.md](../CLAUDE.md) |

> This spec turns the TDD's data strategy into a concrete, buildable plan. Every dataset row must trace to a v1 capability (C1–C4, C6, C7) so coverage is measurable. Licensing rules from TDD §6 are binding.

---

## 1. Principles

1. **License-clean first.** Production training uses only sources cleared for commercial on-prem use: **first-party (our own)**, **PET (MIT)**, and **BPMN MIWG test suite (CC BY 3.0)**. **MaD** and **SAP-SAM** are excluded until their commercial-use licenses are confirmed (TDD S5). **camunda/bpmn-for-research is permanently excluded** (non-commercial).
2. **Capability-traceable.** Every row is tagged with the capability (C#) it trains/evaluates. Coverage is reported per capability (§5).
3. **Validated, not just written.** Any row containing BPMN XML must pass the deterministic toolkit (SpiffWorkflow XSD validation + bpmnlint, TDD §4) before entering the dataset. Invalid XML never enters training data.
4. **Human-reviewed.** Synthetic data is reviewed/corrected by a person before use. Volume never trumps correctness.
5. **Grounded outputs.** For C1, "gold" answers must be consistent with the BPMN 2.0 spec; where practical, include the citing section so the model learns to cite (FR-1).
6. **Versioned & split.** Datasets are versioned; a frozen eval split is held out and never trained on.

---

## 2. Relationship to the training pipeline

The datasets feed the three training stages (TDD §8) plus evaluation:

| Stage | Dataset | Format | Purpose |
|-------|---------|--------|---------|
| 1. Domain adaptation | `corpus_domain.*` | raw text chunks | BPMN vocabulary/semantics (reuse POC spec-chunking) |
| 2. SFT / instruction | `instruction_*.jsonl` | `instruction/input/output` | Follow BPMN task instructions across C1–C4/C6/C7 |
| 3. Preference (DPO/ORPO) | `preference_*.jsonl` | `prompt/chosen/rejected` | Prefer accurate, grounded, well-structured answers |
| Eval (all) | `eval_*.jsonl` | per-capability (see §6) | Frozen benchmark, never trained on |

The existing POC files (`data/bpmn_instruction_dataset.jsonl` — 56 rows; `data/bpmn_dpo_dataset.jsonl` — 39 rows) become the seed of the SFT and preference sets respectively.

---

## 3. Dataset schemas

### 3.1 SFT / instruction rows (extends the POC format)
Keep the POC's `instruction / input / output`, add metadata for traceability and coverage:

```json
{
  "instruction": "Review this BPMN and list any issues with the gateways.",
  "input": "<bpmn:definitions ...> ... </bpmn:definitions>",
  "output": "One issue: the exclusive gateway 'Approved?' (id Gateway_1) has no default flow, risking a stuck token. Fix: add a default sequence flow ...",
  "meta": {
    "capability": "C3",
    "bpmn_elements": ["exclusiveGateway", "sequenceFlow"],
    "diagram_type": "private-process",
    "source": "synthetic-reviewed",
    "spec_ref": "BPMN 2.0 §13.3.2",
    "difficulty": "medium",
    "xml_validated": true,
    "id": "c3-0001"
  }
}
```
- `input` is `""` for pure conceptual Q&A (C1); it carries BPMN XML for C3/C4/C6/C7 and NL descriptions for C2.
- `xml_validated` must be `true` before the row is accepted when XML is present (Principle 3).

### 3.2 Preference rows (extends the POC format)
```json
{
  "prompt": "What is the difference between a Pool and a Lane in BPMN 2.0?",
  "chosen": "A Pool represents a Participant ... Message Flows cross Pools; Lanes are sub-partitions within one Pool ...",
  "rejected": "A Pool and a Lane are basically the same thing ...",
  "meta": { "capability": "C1", "spec_ref": "BPMN 2.0 §9.x", "id": "pref-0001" }
}
```
`rejected` should encode a *realistic* failure mode (see §7.3), not a random wrong answer.

### 3.3 Dual representation (per TDD §4.5)
For any row whose output is a BPMN diagram (C2, and edit examples), store **both** representations:
- the compact **intermediate representation (IR)** the model is trained to emit (JSON node/edge graph, or the IR chosen in TDD spike S6), and
- the canonical **BPMN 2.0 XML** produced by the deterministic IR→XML transform.

This teaches the model to "think" in the lightweight IR (fewer tokens, fewer malformed outputs) while keeping XML as the validated interchange artifact. Example addition to a C2 row:
```json
{
  "instruction": "Generate a BPMN diagram for ...",
  "input": "",
  "output_ir": { "nodes": [...], "edges": [...] },
  "output": "<bpmn:definitions ...>...</bpmn:definitions>",
  "meta": { "capability": "C2", "ir_format": "json-graph", "xml_validated": true, "id": "c2-0001" }
}
```
The XML must be derivable from the IR by the transform (round-trip check) and must pass validation before acceptance.

### 3.4 Encoding fixes needed
The current `data/bpmn_dpo_dataset.jsonl` contains mojibake (e.g. `â€”` for em-dash) from a bad encoding round-trip. **Action:** normalise all files to clean UTF-8 before extending them (backlog item DAT-1).

---

## 4. Data needed per capability

| Cap | Row shape (instruction → output) | BPMN in `input`? |
|-----|----------------------------------|------------------|
| **C1 Q&A** | conceptual question → grounded answer (+ spec ref) | no |
| **C2 Generate** | NL process description → valid BPMN 2.0 XML | no (NL in) / XML out |
| **C3 Review** | "review this diagram" + XML → ranked findings + fixes | yes |
| **C4 Narrate** | "explain this diagram" + XML → plain-English narrative | yes |
| **C6 Automation** | "find automation opportunities" + XML → candidate steps + rationale | yes |
| **C7 Compliance** | "check against rule set R" + XML (+ rules) → pass/fail per rule + evidence | yes |

---

## 5. Coverage matrix (target)

Coverage is tracked on two axes so no element or capability is under-represented.

**Axis 1 — Capability × volume (SFT rows, v1 targets):**
| Cap | Seed (POC) | v1 target |
|-----|:----------:|:---------:|
| C1 | ~56 (shared) | 300+ |
| C2 | 0 | 200+ |
| C3 | few | 200+ |
| C4 | few | 150+ |
| C6 | 0 | 100+ |
| C7 | 0 | 100+ |
| **Total SFT** | ~56 | **~1,000+** |
| **Preference (DPO)** | 39 | **300+** |

*(Targets are starting points; the eval curve in §6 decides when "enough" is reached — grow until eval metrics plateau.)*

**Axis 2 — BPMN element/type coverage (each must appear across C2–C4/C6/C7 rows):**
- Events: start, end, intermediate (message/timer/error), boundary
- Activities: task types (user/service/manual/script), sub-process, call activity, loop/multi-instance
- Gateways: exclusive, parallel, inclusive, event-based
- Flows: sequence flow, message flow, default flow, conditional flow
- Swimlanes: pool, lane (single-pool priority for C2 per TDD §4.4 auto-layout limits)
- Data: data object, data store; artifacts: annotation, group

A coverage report (script) counts rows per (capability × element) and flags gaps.

---

## 6. Evaluation datasets (frozen)

Built from license-clean sources; **never** used for training.

| Eval set | Built from | Measures | Metric (TDD §9) |
|----------|-----------|----------|-----------------|
| `eval_c1_qa.jsonl` | hand-authored gold Q&A + spec | C1 accuracy & grounding | correctness %, RAGAS faithfulness |
| `eval_c2_gen.jsonl` | NL descriptions (PET-derived) w/ reference BPMN | C2 validity & fidelity | XSD-pass %, bpmnlint-clean %, graph-edit-distance |
| `eval_c3_defects.jsonl` | **MIWG** valid diagrams + injected defects | C3 detection | recall/precision on seeded defects |
| `eval_c4_narrate.jsonl` | diagrams + reference narratives | C4 faithfulness | rubric grading |
| `eval_c6_automation.jsonl` | diagrams + labelled automatable steps | C6 usefulness | precision |
| `eval_c7_compliance.jsonl` | diagrams + rule sets + expected results | C7 correctness | precision/recall |

**Seeded-defect generator (C3):** take valid MIWG/first-party diagrams and programmatically inject known defects (remove a default flow, unlabel a task, disconnect an element, unbalance a gateway) with a defect label. This yields a scalable, license-clean C3 benchmark.

---

## 7. Sourcing & generation

### 7.1 First-party expansion (primary)
- Grow the POC instruction/preference sets by hand for C1, and author C2–C4/C6/C7 examples from the coverage matrix.
- Mine the BPMN 2.0 spec (already extracted in the POC) to author grounded C1 Q&A with `spec_ref`.

### 7.2 PET & MIWG (license-clean external)
- **PET (MIT):** use its annotated NL process descriptions to bootstrap C2 (NL→process) and C4 (narration) pairs; the annotations give ground-truth activities/actors/gateways.
- **MIWG (CC BY 3.0):** reference diagrams for C3/C4 eval and as valid inputs for the seeded-defect generator. **Attribution required** — record it in the dataset card.

### 7.3 Synthetic generation with a validation loop
For C2–C7 volume, generate candidates then **filter through the deterministic toolkit** so only valid data survives:

```
Author/generate candidate (NL + BPMN XML)
   → bpmn-auto-layout (add DI)
   → SpiffWorkflow BpmnValidator (XSD/schema)   ─ fail → discard/repair
   → bpmnlint (rule check)                        ─ fail → discard/repair
   → human review (correctness, clarity)          ─ fail → fix
   → accept into dataset (xml_validated=true, source="synthetic-reviewed")
```

**Realistic `rejected` answers for preference data (§3.2):** generate plausible-but-wrong responses (subtle factual error, missing exception path, over-generic advice) rather than obvious nonsense — this trains the model against the failure modes that actually occur. The POC DPO file already models this well; extend that style.

### 7.4 What NOT to do
- ❌ Do not train on MaD or SAP-SAM until licensing is confirmed (S5).
- ❌ Do not use camunda/bpmn-for-research at all.
- ❌ Do not admit any BPMN XML that fails validation.

---

## 8. Quality control

- **Two-pass review** for synthetic rows: generator + independent human check.
- **Automated gates (CI on the data repo):** JSON schema valid; required `meta` fields present; BPMN `input`/`output` passes SpiffWorkflow + bpmnlint; no mojibake (UTF-8 clean); no duplicate `id`s or near-duplicate content.
- **Inter-source dedup:** ensure eval diagrams/questions do not leak into training (exact + fuzzy match).

---

## 9. Versioning, splits & layout

- **Split:** ~80/10/10 train/val/test *per capability*; the test split is the frozen eval set (§6) and is never trained on.
- **Versioning:** date-stamped dataset versions; a `DATASET_CARD.md` per set records source, license, size, coverage, and attribution (MIWG).
- **Proposed layout:**
```
data/
  raw/                     # source material (spec text, PET, MIWG) — untracked large files per .gitignore
  domain/                  # stage-1 corpus chunks
  instruction/
    instruction_v2.jsonl   # SFT (extends bpmn_instruction_dataset.jsonl)
  preference/
    preference_v2.jsonl    # DPO/ORPO (extends bpmn_dpo_dataset.jsonl, UTF-8 fixed)
  eval/                    # frozen per-capability eval sets (§6)
  scripts/                 # validate_rows.py, coverage_report.py, inject_defects.py
  DATASET_CARD.md
```

---

## 10. Deliverables & sequence

| # | Deliverable | Depends on |
|---|-------------|-----------|
| D1 | UTF-8 fix + re-layout of existing POC datasets (DAT-1) | — |
| D2 | `validate_rows.py` (SpiffWorkflow + bpmnlint gate) + `coverage_report.py` | TDD §4 toolkit installed |
| D3 | `inject_defects.py` + `eval_c3_defects.jsonl` from MIWG | D2, MIWG downloaded |
| D4 | C1 gold Q&A eval set + expanded C1 SFT/preference rows | — |
| D5 | C2 NL→BPMN rows (PET-bootstrapped) through the validation loop | D2, PET |
| D6 | C4 narration, C6 automation, C7 compliance rows + eval sets | D2 |
| D7 | Coverage report showing v1 targets met (§5) | D1–D6 |

---

## 11. Risks

| Risk | Mitigation |
|------|-----------|
| License contamination from excluded corpora | Hard rule: only first-party + PET + MIWG in production; CI checks `source` field |
| Synthetic data teaches wrong patterns | Mandatory validation loop (§7.3) + human review |
| Eval leakage into training | Per-capability split with fuzzy-dedup gate (§8) |
| Attribution non-compliance (MIWG CC BY) | Record attribution in `DATASET_CARD.md` |
| Coverage blind spots | Automated (capability × element) coverage report (§5) gates release |

---

*End of document. D1–D2 are the unblocking first steps; everything else builds on the validation gate.*
