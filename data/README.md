# `data/` — contents and purpose

This folder holds the datasets for the BPMN Intelligence Assistant, plus the inputs and
source material used to generate them. Files are grouped by **role**, with a clear note on
what is needed for **training** vs **regeneration** vs **runtime** vs **reference**.

> Legend — **Role**: `TRAIN` = fed to model fine-tuning · `EVAL` = held-out evaluation ·
> `GEN-INPUT` = build-time input to a generator script · `RUNTIME` = also used by the live
> product · `REFERENCE` = grounding/source material · `SUPERSEDED` = replaced, kept only as
> a regeneration source.

## Training sets — `data/instruction/` (SFT) — **TRAIN**
Supervised fine-tuning rows, one capability family each. All tagged `meta.capability`, all
pass `validate_rows.py`.

| File | Capability | Rows (approx) | Produced by |
|------|-----------|:----:|-------------|
| `instruction_v2.jsonl` | C1/C2 (tagged legacy) | 57 | `tag_capabilities.py` |
| `instruction_c1_authored.jsonl` | C1 (hand-authored) | 12 | authored |
| `instruction_c1_kb.jsonl` | C1 (KB-generated Q&A) | 242 | `gen_c1_qa.py` ← `seeds/bpmn_kb.json` |
| `instruction_c2.jsonl` | C2 (NL → BPMN XML) | 410 | `build_c2_dataset.py` |
| `instruction_c3.jsonl` | C3 (review/defects) | ~240 | `inject_defects.py` |
| `instruction_c4.jsonl` | C4 (narration) | ~410 | `build_analysis_dataset.py` |
| `instruction_c6.jsonl` | C6 (automation) | ~410 | `build_analysis_dataset.py` |
| `instruction_c7.jsonl` | C7 (compliance) | ~410 | `build_analysis_dataset.py` |

## Preference sets — `data/preference/` (DPO) — **TRAIN**
Chosen/rejected pairs for preference alignment.

| File | Rows | Produced by |
|------|:----:|-------------|
| `preference_v2.jsonl` | 40 | `tag_capabilities.py` (tagged legacy DPO) |
| `preference_generated.jsonl` | 260 | `build_preference_dataset.py` (validation-backed pairs) |

## Evaluation sets — `data/eval/` — **EVAL**
Held-out benchmarks per capability. **Never** used for training (the release gate checks
for train/eval leakage). Needed to measure the FDD KPIs.

| File | Capability | Rows |
|------|-----------|:----:|
| `eval_c1_qa.jsonl` | C1 gold Q&A | 12 |
| `eval_c2_gen.jsonl` | C2 generation | 6 |
| `eval_c3_defects.jsonl` | C3 seeded-defects | ~58 |
| `eval_c4_narrate.jsonl` | C4 narration | ~17 |
| `eval_c6_automation.jsonl` | C6 automation | ~17 |
| `eval_c7_compliance.jsonl` | C7 compliance | ~17 |

## Generation inputs — `data/seeds/` — **GEN-INPUT** (+ one **RUNTIME**)
Authored inputs consumed by the generator scripts. **Not** training data themselves —
their content is already baked into the datasets above. Needed only to **regenerate/scale**.

| File | Consumed by | Note |
|------|-------------|------|
| `bpmn_kb.json` | `gen_c1_qa.py` | 134-concept curated BPMN knowledge base → C1 Q&A |
| `c2_seeds_firstparty.jsonl` | `build_c2_dataset.py` | hand-authored NL+IR C2 seeds |
| `c2_eval_seeds.jsonl` | `build_c2_dataset.py --eval` | held-out NL+IR seeds → C2 eval |
| `compliance_rules.json` | `build_analysis_dataset.py` **and** `analyze_bpmn.py` | **RUNTIME**: also the live rule set the C7 checker reads; organisations edit this |

## Reference / grounding — **REFERENCE**
| File | Purpose |
|------|---------|
| `formal-11-01-03.pdf` | The official OMG **BPMN 2.0 specification** (~7 MB). Grounding source for the RAG layer and domain-adaptation corpus (TDD §5, P1). Not part of the current SFT/DPO rows, but a key project asset. |

## Source corpora — `data/raw/` — **GEN-INPUT** (git-ignored)
Downloaded third-party corpora (thousands of files), **not committed to git**. Needed only
to **regenerate** the derived datasets, not to train.

| Sub-folder | Source | License | Feeds |
|-----------|--------|---------|-------|
| `bpmn-miwg-test-suite/` | BPMN MIWG test suite | CC BY 3.0 | C3/C4/C6/C7 train+eval (rich real diagrams) |
| `hdBPMN/` | dwslab/hdBPMN | CC BY 4.0 | C4/C6/C7 eval (real-world slice) |
| `PET/` | patriziobellan/PET | MIT | C2 seed bootstrap (`pet_to_ir.py`) |
| `c2_seeds_generated.jsonl`, `c2_seeds_pet.jsonl` | generated | — | intermediate C2 seeds (regenerable) |

## Superseded — **DELETED**
The original POC datasets have been **removed** (not needed for training):
- `bpmn_instruction_dataset.jsonl` → replaced by `instruction/instruction_v2.jsonl` (tagged).
- `bpmn_dpo_dataset.jsonl` → replaced by `preference/preference_v2.jsonl` (tagged, UTF-8 repaired).

`instruction_v2.jsonl` / `preference_v2.jsonl` are now the **canonical tagged sources**.
Re-running `tag_capabilities.py` from the raw POC files would require restoring the two
deleted files from git history first (`git checkout <rev> -- data/bpmn_*_dataset.jsonl`).

---

## Diagram-interchange (DI) handling
- **Analysis tasks (C3/C4/C6/C7):** the BPMN XML in the `input` field has its `<bpmndi:BPMNDiagram>`
  (shape coordinates / edge waypoints) **stripped** — DI is noise for semantic review/narration and
  was ~half the tokens. The semantic model is untouched and the XML stays schema-valid (DI is
  optional in BPMN 2.0). This roughly halves sequence length and cuts truncation from ~35% to ~1%.
- **Generation task (C2):** the `output` BPMN XML **keeps full DI** so generated diagrams render.
- **Inference consistency:** the assistant's orchestrator strips DI the same way before handing an
  uploaded diagram to the model for analysis (see `src/data_pipeline/analyze_bpmn.py::strip_di`).

## What is needed for a training run
- **Required:** `data/instruction/*.jsonl` (SFT) + `data/preference/*.jsonl` (DPO).
- **Required for evaluation:** `data/eval/*.jsonl`.
- **Not required for training** (but keep for regeneration/runtime/reference): `data/seeds/`,
  `data/raw/`, `data/formal-11-01-03.pdf`, and the two superseded POC files.

To regenerate everything from inputs, see `src/data_pipeline/README.md`.
