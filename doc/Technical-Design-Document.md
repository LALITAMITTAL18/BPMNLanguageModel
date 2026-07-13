# Technical Design Document — BPMN Intelligence Assistant

| | |
|---|---|
| **Document** | Technical Design Document (TDD) |
| **Product** | BPMN Intelligence Assistant |
| **Version** | 0.1 (Draft) |
| **Author** | Lalita Mittal |
| **Date** | 2026-07-10 |
| **Status** | Draft for review |
| **Governs** | *How* to build what the FDD specifies |
| **Constrained by** | [`doc/Functional-Design-Document.md`](Functional-Design-Document.md) (frozen) and [`CLAUDE.md`](../CLAUDE.md) |

> This TDD must stay consistent with the frozen FDD. Where a technical constraint would conflict with the FDD, that conflict is surfaced to the sponsor rather than resolved by diverging (per CLAUDE.md §4). Every design choice below is traced to a capability (C#) / requirement (FR-#).

> **Evidence basis.** The technology recommendations here are grounded in a deep-research pass (26 sources fetched, 25 claims adversarially verified, 23 confirmed) run on 2026-07-10. Confidence is marked per section: **[Verified]** = confirmed by ≥3-vote adversarial check against primary sources; **[Indicative]** = drawn from search/secondary sources, not independently verified — treat as a starting point to validate in a spike. Sources are listed in §12.

---

## 1. Locked Constraints (from the FDD)

These are non-negotiable inputs to every decision in this document:

- **Self-hosted / on-prem only.** No third-party hosted LLM APIs on any production path. Process data never leaves the tenant.
- **Generic, industry-agnostic BPMN 2.0** in v1; interchange format is BPMN 2.0 XML (`.bpmn`).
- **v1 capability scope:** C1 (Q&A/Tutor), C2 (Generate), C3 (Review), C4 (Narrate), C6 (Automation detection), C7 (Compliance check).
- **Delivery:** standalone chat app first; modeller plugin later (P4).
- **Licensing:** every model, dataset, and library used in production must permit **commercial, on-prem** use.

**Immediate consequence:** the POC's `TinyLlama-1.1B` is too small for production reasoning, and the design cannot lean on a hosted model to compensate. Accuracy is therefore carried by three cooperating layers — a **larger self-hosted fine-tuned model**, **retrieval grounding**, and **deterministic BPMN tools** — not by the model alone.

---

## 2. Architecture Overview

```
 ┌───────────────────────────────────────────────────────────────┐
 │  Standalone Chat UI  (chat + .bpmn upload + diagram preview)    │  ← delivery (FR-10, FR-12)
 └────────────────────────────────┬──────────────────────────────┘
                                   │
 ┌────────────────────────────────▼──────────────────────────────┐
 │  Agent Orchestrator  (intent routing, tool-calling, session)   │  ← all capabilities
 │  local tool-calling via the model's native function-calling    │
 └───┬──────────────┬───────────────┬──────────────┬─────────────┘
     │              │               │              │
 ┌───▼─────────┐ ┌──▼───────────┐ ┌─▼────────────┐ ┌▼──────────────────┐
 │ Fine-tuned  │ │ Retrieval    │ │ BPMN Toolkit │ │ Rule / Analysis   │
 │ LLM         │ │ (RAG over    │ │ parse /      │ │ Engines           │
 │ Qwen3-14B   │ │ BPMN 2.0     │ │ validate /   │ │ lint, compliance, │
 │ (LoRA/DPO)  │ │ spec, cited) │ │ generate /   │ │ automation,       │
 │             │ │ embeddings + │ │ auto-layout  │ │ structural checks │
 │             │ │ vector store │ │              │ │                   │
 └─────────────┘ └──────────────┘ └──────────────┘ └───────────────────┘
        │                │                │                  │
        └────────────────┴────────────────┴──────────────────┘
                     All components run inside the tenant (on-prem)
```

**Separation of concerns (the core design principle):**
- The **LLM** provides language understanding, explanation, and drafting.
- **Retrieval** supplies verifiable, citable facts from the BPMN 2.0 spec (kills hallucination for C1).
- **Deterministic tools** own every hard correctness judgement — XSD/schema validation, lint rules, structural graph analysis, layout. The model *orchestrates and explains* these tools; it does not adjudicate correctness itself. (This directly addresses the research caveat that generation libraries do **not** guarantee schema-correct output — see §4.3.)

---

## 3. Production Model

### 3.1 Recommendation — Qwen3-14B  **[Verified]**
| Attribute | Value |
|-----------|-------|
| Model | `Qwen/Qwen3-14B` |
| License | **Apache 2.0** — commercial + on-prem permitted |
| Size | 14.8B params (13.2B non-embedding), 40 layers, GQA (40 Q / 8 KV heads) |
| Notable | Switchable thinking / non-thinking modes; **native tool-calling + MCP** support (via Qwen-Agent) |
| Why it fits | License-clean upgrade from TinyLlama; agentic tool-calling is exactly what the orchestrator (§7) needs; size is tractable on a single modern data-centre GPU when quantized |
| Sources | huggingface.co/Qwen/Qwen3-14B; qwenlm.github.io/blog/qwen3; github.com/QwenLM/Qwen3 |

**Rationale:** the assistant's job is heavily *tool-driven* (validate, lint, generate, retrieve). A model with first-class function-calling reduces orchestration glue and improves reliability. Apache 2.0 removes all commercial/on-prem licensing doubt.

### 3.2 Sizing & alternatives
- **Smaller footprint:** Qwen3-8B (same family/license) if GPU budget is tight; expect weaker complex reasoning.
- **Larger quality:** Qwen3-32B (same license) if hardware allows — re-benchmark before committing.
- **Cross-family check:** re-benchmark against current Apache/MIT peers (Mistral, Gemma-license variants, newer Qwen releases) at selection time. *[Caveat: the LLM landscape moves fast; Qwen3 is a 2025 release — treat §3 as "best at time of research," not permanent.]*

### 3.3 Serving & quantization  **[Indicative]**
- Serve with a local inference engine (vLLM or Ollama/llama.cpp for GGUF) inside the tenant.
- Quantization options to evaluate: **GGUF / AWQ / GPTQ at 4-bit** to fit a single GPU; measure quality delta on the eval set (§9) before choosing. Exact VRAM footprint per quant is an **open question / spike** (§11).
- ⚠️ **Do not assume** fine-tuning preserves native tool-calling/thinking behaviour — verify post-fine-tune (spike, §11).

---

## 4. BPMN Toolkit (deterministic correctness layer)

This layer does the work the model must **not** be trusted to do alone. Two mature, **MIT-licensed** ecosystems are recommended; use both.

### 4.1 Python — SpiffWorkflow  **[Verified]**
- Pure-Python BPMN 2.0 parser (`BpmnParser`, plus DMN/Spiff variants) and **`BpmnValidator` that validates against the BPMN 2.0 spec** (schema-based via lxml; also catches duplicate IDs). Custom-extension specs can be imported.
- **Use for:** server-side parsing, XSD/schema validation, structural inspection feeding C3/C4/C6.
- Source: spiffworkflow.readthedocs.io/en/latest/bpmn/parsing.html. *(Note: its Camunda parser variant is deprecated.)*

### 4.2 JavaScript — the bpmn.io stack  **[Verified]**
| Package | Role | Capability |
|---------|------|-----------|
| `bpmn-moddle` | Read/write BPMN 2.0 XML (`fromXML`/`toXML`) | C2 generate, C3/C4 parse |
| `bpmn-js` | Render + edit diagrams in browser; `importXML` returns warnings | UI preview, C4 |
| `bpmn-auto-layout` | Generate missing **DI (diagram-interchange) coordinates** so LLM-generated XML renders | C2 |
| `bpmnlint` | Configurable/pluggable lint rules (e.g. `conditional-flows`, `end-event-required`, `label-required`, `start-event-required`) with error/warning severities | C3, C5(later), C7 |

Sources: github.com/bpmn-io/{bpmn-moddle, bpmn-js, bpmn-auto-layout, bpmnlint}. All MIT.

### 4.3 Critical correctness note  **[Verified — refuted claim]**
Research **refuted** the claim that `bpmn-moddle` guarantees schema-correct validated output. **Therefore:** never rely on the generation library alone for correctness. The pipeline for any generated/edited BPMN is (see §4.5 for the representation step that precedes it):

```
LLM emits intermediate representation (IR: JSON/graph) → deterministic IR→BPMN-XML transform
   → bpmn-auto-layout (add DI) → SpiffWorkflow BpmnValidator (XSD/schema)
   → bpmnlint (rule checks) → only then surface to user
```

If validation/lint fails, errors are fed back to the model for a repair pass (bounded retries) before the diagram is shown.

### 4.4 Auto-layout limitations  **[Verified]**
`bpmn-auto-layout` adds DI to coordinate-less XML but does **not** fully handle collaborations (only the first participant), collapsed sub-processes, groups/annotations/associations/message flows, or multi-pool/lane layouts. **Design implication:** v1 C2 generation should target **single-pool, single-process diagrams** for reliable auto-layout; multi-pool collaboration layout is a known gap to scope explicitly (backlog item, and note the limitation to users rather than emit a broken diagram — FDD NFR auditability).

### 4.5 Model I/O representation strategy — dual representation  **[Verified]**
The model should **not** be asked to emit verbose BPMN 2.0 XML directly. Evidence shows a lightweight **intermediate representation (IR)** is markedly better for LLM generation and editing, with XML produced by a deterministic transform afterwards.

- **Reasoning/generation layer (what the LLM emits):** a compact IR — a **JSON node/edge graph** (or Mermaid-style DSL) capturing elements, flows, gateways, lanes. The bpmn.io "BPMN Assistant" work uses a JSON IR with function-calling for atomic edits and reports it **outperforms direct-XML editing with ~43% lower latency and >75% fewer output tokens**; comparative studies find graph/Mermaid representations are far more token-compact than BPMN XML (>90% reduction). Fewer tokens + simpler grammar ⇒ fewer malformed outputs.
- **Interchange layer (what tools/users get):** valid **BPMN 2.0 XML**, produced from the IR by a deterministic converter (via `bpmn-moddle`), then laid out (`bpmn-auto-layout`) and validated (§4.3). XML remains the contract with modellers/engines (Camunda, Signavio) and the FDD's stated interchange format.

**Design implications:**
- Training data should be **dual-representation** (store both the IR and the canonical XML for each example) so the model learns to think in IR and the transform stays deterministic — folded into the [Training-Data Build Spec](Training-Data-Build-Spec.md).
- For **editing** existing diagrams (later capability), parse XML → IR, apply LLM edit operations on the IR, re-emit XML. This makes edits atomic and diffable.
- The exact IR (JSON graph vs. Mermaid vs. DOT) is a **spike** (§11, S6) — pick by generation accuracy + round-trip fidelity on our eval set.
- Sources: arXiv 2509.24592 (BPMN Assistant, JSON IR); arXiv 2507.11356 (comparative representation analysis, CC BY 4.0).

---

## 5. Retrieval / RAG Layer (grounding for C1)  **[Indicative]**

Grounds Q&A answers in the BPMN 2.0 spec so every substantive claim is citable (FR-1, FR-11). The spec PDF (`data/formal-11-01-03.pdf`) is already chunked in the POC — reuse that pipeline.

| Component | Candidate (self-hostable, permissive license) | Notes |
|-----------|-----------------------------------------------|-------|
| Embedding model | **Qwen3-Embedding** (Apache 2.0) or **BGE-M3** (MIT) | Both self-hostable; small VRAM; strong MTEB standing. Pick via retrieval-quality eval on BPMN spec queries. |
| Vector store | **Qdrant**, **pgvector** (Postgres), or **FAISS** | Qdrant/pgvector for a running service; FAISS for an embedded index. Choose by ops preference — all self-hostable. |
| Retrieval eval | **RAGAS** (faithfulness, answer relevancy, context precision/recall) | Use to tune chunking/top-k and to gate C1 quality. |

⚠️ These are the least-verified recommendations in this document (research coverage gap — §11). Run a short RAG spike to confirm embedding model + store before committing.

**Design detail:** answers must carry citations to spec sections (FR-1). Store section/heading metadata with each chunk so the model can cite "BPMN 2.0 §10.x". If retrieval returns nothing relevant, the assistant must say so rather than fabricate (FR-11).

---

## 6. Datasets

The sponsor asked specifically for a dataset search across Hugging Face, Kaggle, GitHub, and academic sources. Results below, with **license status flagged** against the on-prem commercial constraint.

### 6.1 Usable for a commercial on-prem product
| Dataset | What it is | Size | License | Use | URL |
|---------|-----------|------|---------|-----|-----|
| **PET** | Gold-standard NL→process-extraction corpus; annotated activities, actors, activity data, gateways, conditions; NER + relation-extraction tasks | 45 descriptions (47 orig, 2 discarded) | **MIT** ✅ | C2 (NL→process), C4 (narration), eval | huggingface.co/datasets/patriziobellan/PET · arXiv 2203.04860 |
| **BPMN MIWG Test Suite** | Reference BPMN 2.0 test cases (`.bpmn` XML + diagrams): Series A (basic), B (Descriptive/Analytic conformance), C (advanced real-world) | ~19–21 files | **CC BY 3.0** ✅ (attribution) | Validation/eval corpus for C2/C3 | github.com/bpmn-miwg/bpmn-miwg-test-suite |
| **TXT2BPMN model** | T5-Small fine-tuned for text→BPMN; the *model artifact* is MIT | model on 30k pairs | **MIT** ✅ (model tag) | Reference/baseline for C2 | huggingface.co/fachati/TXT2BPMN |

### 6.2 Attractive at scale but license must be verified before use
| Dataset | What it is | Size | License status | URL |
|---------|-----------|------|----------------|-----|
| **MaD** | NL business-process-description ↔ BPMN(DOT) pairs across 15 domains | ~30,000 (≈26,000 after cleaning) | ⚠️ **Data license separate from the MIT model tag — unverified for commercial use.** Do not train on it until confirmed. | arXiv 2512.12063 · ResearchGate 372862697 |
| **SAP-SAM** | Very large corpus, mainly BPMN models from academic.signavio.com | ~1,021,471 models | ⚠️ **Commercial-use license NOT confirmed** by research. Verify before any use. | arXiv 2208.12223 |

### 6.3 Explicitly EXCLUDED (non-commercial)  **[Verified]**
| Dataset | Why excluded |
|---------|--------------|
| **camunda/bpmn-for-research** (>3,700 `.bpmn` files) | Terms of Use: *"academic and research purposes only"* and *"Commercial use of the content of this repository is not allowed."* **Must not be used** in this product. (Verified live 2026-07-10.) |

### 6.4 First-party data (recommended primary source)
Given the licensing minefield above, the most reliable path is to **grow the POC's own datasets** (`data/bpmn_instruction_dataset.jsonl`, `data/bpmn_dpo_dataset.jsonl`) plus a **synthetically generated, human-reviewed** corpus of NL↔BPMN pairs and flawed/fixed diagrams. This sidesteps third-party license risk entirely and lets us target our exact capabilities. See §8.

---

## 7. Agent Orchestration  **[Indicative]**

The orchestrator interprets the user's intent, calls the right tool(s), and composes a grounded answer — this *is* the "agent" the FDD promises.

- **Approach:** use Qwen3's **native tool-calling** to expose the BPMN toolkit (§4), retrieval (§5), and rule engines (§9-analysis) as callable tools. Candidate frameworks: **Qwen-Agent** (tightest fit with Qwen3 tool-calling/MCP), **LangGraph** (explicit state-machine control), or a thin custom MCP layer.
- **Tool-error feedback loop:** validation/lint errors from SpiffWorkflow/bpmnlint are returned to the model as structured messages so it can self-correct (bounded retries), per §4.3.
- **Session/state:** maintain conversation context and any uploaded diagram across turns (FR-10).
- ⚠️ Framework choice is an open question (§11) — validate local tool-calling reliability with Qwen3 in a spike before committing.

---

## 8. Fine-Tuning & Data Pipeline  **[Indicative]**

Keep the POC's proven 3-stage shape, upgraded to Qwen3-14B and larger data.

**Technique stack:** **QLoRA** (4-bit) for memory-efficient adaptation on a single large GPU → **SFT** (instruction tuning) → **preference alignment (DPO/ORPO)**. ORPO is worth evaluating as it folds preference alignment into one stage.

| Stage | Purpose | Data |
|-------|---------|------|
| 1. Domain adaptation | BPMN vocabulary/semantics | BPMN 2.0 spec text (existing pipeline) |
| 2. SFT / instruction tuning | Follow BPMN task instructions across C1–C4/C6/C7 | Expanded instruction set (target: several hundred+ diverse, reviewed examples) + PET |
| 3. DPO/ORPO | Prefer accurate, well-structured, grounded answers | Expanded preference pairs |

**Tooling to evaluate:** Axolotl, Unsloth, TRL, or LLaMA-Factory (all support QLoRA + DPO/ORPO). Choose by throughput and Qwen3 support.

**Data pipeline:** curate → deduplicate → hold out a frozen eval split → version datasets. Prioritise **first-party + PET + MIWG** (license-clean). Every training row should trace to a capability so coverage is measurable.

⚠️ **Do not over-index on the InstruBPM result.** Research **refuted** the specific claim that a LoRA-tuned Qwen3-4B "InstruBPM" hits BLEU 83 / R-GED 99.4% and beats larger models — treat those numbers as unproven and set our own baselines.

---

## 9. Evaluation Strategy

Ties directly to the FDD KPIs (§10 there). Build the eval harness alongside development.

| Capability | What to measure | Method / metric |
|-----------|-----------------|-----------------|
| C1 Q&A | Factual correctness + grounding | Gold Q&A set graded for accuracy; **RAGAS faithfulness / context precision** for citation grounding |
| C2 Generate | Valid, importable output | % passing **SpiffWorkflow XSD validation** + **bpmnlint**; import-clean in bpmn-js. Prefer **structural similarity (graph edit distance / R-GED)** over n-gram BLEU/ROUGE for XML |
| C3 Review | Defect detection | Recall/precision on a **seeded-defect corpus** (build from MIWG + first-party flawed diagrams) |
| C4 Narrate | Faithful description | Human/rubric grading vs. ground-truth structure |
| C6 Automation | Useful, correct candidates | Precision on labelled automation-opportunity set |
| C7 Compliance | Rule-hit accuracy | Precision/recall vs. a labelled rule-check set |

**Note [Verified caveat]:** for XML generation, structural metrics (graph edit distance) are more meaningful than n-gram overlap. Agent-level evaluation (tool-call correctness, task completion) via a framework like Confident-AI/DeepEval is worth adopting.

---

## 10. Deployment (on-prem)

- **All components in-tenant:** model serving, embedding model, vector store, BPMN toolkit (Python service + Node service for bpmn.io), rule engines, and the chat UI. No egress of diagrams or prompts.
- **Topology:** GPU host for LLM + embeddings; CPU services for the BPMN toolkit and rule engines; the chat UI as a web app.
- **Hardware:** a single modern data-centre GPU should serve a 4-bit Qwen3-14B; confirm exact VRAM in the sizing spike (§11).
- **Auditability (FR-12, NFR):** log tool calls, validation results, and generated artefacts; make findings/diagrams exportable.

---

## 11. Open Questions & Required Spikes

Carried forward from research coverage gaps and caveats. Resolve each with a small time-boxed spike before the corresponding build phase.

1. **RAG stack (S1):** confirm embedding model (Qwen3-Embedding vs BGE-M3) + vector store (Qdrant/pgvector/FAISS) on real BPMN-spec queries. *(Least-verified area.)*
2. **Model serving/quant (S2):** measure VRAM + quality for Qwen3-14B at 4-bit (GGUF/AWQ/GPTQ); confirm fine-tuning preserves tool-calling.
3. **Orchestration (S3):** validate local Qwen3 tool-calling reliability (Qwen-Agent vs LangGraph vs custom MCP) incl. error-feedback loop.
4. **Evaluation (S4):** stand up BPMN-correctness (R-GED) + RAGAS-faithfulness harness; set our own baselines (ignore unverified InstruBPM numbers).
5. **Dataset licensing (S5):** get written confirmation on **SAP-SAM** and **MaD** commercial-use status; until then, rely on first-party + PET + MIWG only.
6. **Intermediate representation (S6):** choose the IR the model emits (JSON node/edge graph vs. Mermaid vs. DOT) by measuring generation accuracy + lossless round-trip fidelity to BPMN XML on our eval set (§4.5).

---

## 12. Capability → Component Traceability

| Capability | Model | RAG | BPMN Toolkit | Rule/Analysis | Orchestrator |
|-----------|:----:|:---:|:-----------:|:-------------:|:------------:|
| C1 Q&A | ✓ | ✓ | | | ✓ |
| C2 Generate | ✓ | | ✓ (moddle + auto-layout + validate) | | ✓ |
| C3 Review | ✓ | | ✓ (SpiffWorkflow + bpmnlint) | ✓ | ✓ |
| C4 Narrate | ✓ | | ✓ (parse) | | ✓ |
| C6 Automation | ✓ | | ✓ (parse/structure) | ✓ | ✓ |
| C7 Compliance | ✓ | | ✓ (parse) | ✓ (configurable rules) | ✓ |

---

## 13. Sources

**Verified primary sources**
- Qwen3-14B: huggingface.co/Qwen/Qwen3-14B · qwenlm.github.io/blog/qwen3 · github.com/QwenLM/Qwen3
- PET dataset: huggingface.co/datasets/patriziobellan/PET · arXiv 2203.04860
- MaD / TXT2BPMN: arXiv 2512.12063 · huggingface.co/fachati/TXT2BPMN · ResearchGate 372862697
- SAP-SAM: arXiv 2208.12223
- bpmn-for-research (excluded): github.com/camunda/bpmn-for-research
- MIWG test suite: github.com/bpmn-miwg/bpmn-miwg-test-suite
- SpiffWorkflow: spiffworkflow.readthedocs.io/en/latest/bpmn/parsing.html
- bpmn.io stack: github.com/bpmn-io/{bpmn-moddle, bpmn-js, bpmn-auto-layout, bpmnlint}
- bpmn-auto-layout usage + JSON intermediate representation in LLM generation: arXiv 2509.24592 (BPMN Assistant)
- Comparative analysis of process-model representations for LLMs (BPMN XML vs JSON vs Mermaid vs DOT): arXiv 2507.11356 (CC BY 4.0)

**Indicative / secondary sources** (RAG, training, eval — validate in spikes)
- Embedding models: bentoml.com/blog/a-guide-to-open-source-embedding-models · aimultiple.com/open-source-embedding-models
- Vector databases: firecrawl.dev/blog/best-vector-databases
- RAG eval (RAGAS): cohorte.co (RAGAS deep dive)
- Fine-tuning: futureagi.com/blog/llm-fine-tuning-guide-2025 · dev.to (Axolotl vs Unsloth vs TRL vs LLaMA-Factory) · codersarts (QLoRA+DPO)
- Agent/LLM eval: atlan.com/know/llm-evaluation-frameworks-compared · confident-ai.com/blog/llm-agent-evaluation-complete-guide

---

*End of document. §11 spikes should be resolved and folded back into v0.2 before P1 build starts.*
