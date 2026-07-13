# Functional Design Document — BPMN Intelligence Assistant

| | |
|---|---|
| **Document** | Functional Design Document (FDD) |
| **Product** | BPMN Intelligence Assistant ("the Assistant") |
| **Version** | 0.2 (Draft) |
| **Author** | Lalita Mittal |
| **Date** | 2026-07-10 |
| **Status** | Draft for review |

> **Scope decisions confirmed with sponsor (v0.2):**
> 1. **Delivery:** standalone chat app first, modeller plugin in a later phase.
> 2. **Model:** **must be self-hosted / on-prem** — process data cannot leave the tenant. No third-party hosted LLM.
> 3. **Domain:** generic, industry-agnostic BPMN in v1; any industry/organisation specialisation deferred to a later phase.
> 4. **v1 capability scope:** core three (C1 Q&A, C2 Generate, C3 Review) **plus** C4 Diagram Narration, C6 Automation Detection, C7 Compliance Check.

---

## 1. Purpose of this Document

This document defines **what** the BPMN Intelligence Assistant will do, for **whom**, and **why** — before we decide *how* to build it in detail. It translates the current research pipeline (a fine-tuned BPMN language model) into a product that a non-technical **business user** can rely on.

The end goal, in the sponsor's words:

> "An agent that can answer any human question related to BPMN, suggest a BPMN schema, and suggest what should be improved in a schema — and deliver real, practical benefit to a business user of BPMN."

This FDD is the contract between the idea and the build. It is intentionally capability-first and technology-light; a separate Technical Design Document (TDD) will specify architecture, model, and infrastructure choices.

---

## 2. Background & Current State

The repository already contains a working three-stage training pipeline that adapts a small open model (`TinyLlama-1.1B`) to the BPMN 2.0 domain:

| Stage | Notebook | Technique | Purpose |
|-------|----------|-----------|---------|
| 1 — Domain adaptation | `1.0-non-instruction-finetuning-on-base-model.ipynb` | Causal LM fine-tuning (LoRA) on raw text extracted from the official BPMN 2.0 spec PDF | Teach the model BPMN vocabulary, structure & semantics |
| 2 — Instruction tuning | `2.0-instruction-finetuning-on-1.0-model.ipynb` | Instruction fine-tuning on ~56 Q&A pairs | Teach the model to answer questions, not just continue text |
| 3 — Preference alignment | `3.0-DPO-on-2.0-model.ipynb` | Direct Preference Optimisation on ~39 chosen/rejected pairs | Prefer accurate, well-structured answers over shallow ones |
| 4 — Evaluation | `4.0-Test-All-Steps.ipynb` | Side-by-side generation across all three stages | Compare progress |

**Data assets today:** the official BPMN 2.0 spec (`data/formal-11-01-03.pdf`), `data/bpmn_instruction_dataset.jsonl` (56 rows), `data/bpmn_dpo_dataset.jsonl` (39 rows).

**Implication for this design:** we have a proven *foundation model of BPMN knowledge*, but not yet a *product*. A knowledgeable model is necessary but not sufficient. The Assistant must add: grounded/verifiable answers, the ability to read and write real BPMN files (BPMN 2.0 XML), validation logic, a conversational agent layer, and a user-facing interface.

---

## 3. Vision & Goals

### 3.1 Vision
A single conversational assistant that any business user can ask *anything* about BPMN — from "what is a message event?" to "review my order-to-cash process and tell me what's wrong" — and get accurate, actionable, standards-grounded answers.

### 3.2 Goals
1. **Explain** BPMN concepts and any specific diagram in plain language.
2. **Author** — generate a valid BPMN 2.0 schema from a natural-language process description.
3. **Improve** — validate a BPMN diagram against the standard and best practices, and recommend concrete fixes.
4. **Advise** — surface higher-value insights (automation candidates, bottlenecks, compliance gaps, RACI clarity) that help a business improve its processes, not just its diagrams.

### 3.3 Non-Goals (out of scope for v1)
- Being a full BPMN *modelling canvas* (drag-and-drop editor). The Assistant produces/consumes BPMN files; a modelling tool (e.g., bpmn.io, Camunda Modeler, Signavio) remains the editor.
- Executing/orchestrating live processes (a BPM engine's job).
- Full process-mining from event logs (considered as a later phase / integration).
- A **modeller plugin** in v1 — v1 ships as a **standalone chat app**; embedding into a modeller is a later phase (confirmed decision).
- Use of any **third-party hosted LLM** — deployment is **self-hosted / on-prem** only (confirmed decision).
- **Industry-specific** templates and compliance packs in v1 — generic, industry-agnostic BPMN first (confirmed decision).

---

## 4. Target Users (Personas)

| Persona | Who they are | What they need from the Assistant |
|---------|-------------|-----------------------------------|
| **Business Analyst (primary)** | Draws and documents processes | Generate first-draft diagrams, validate, explain notation, enforce conventions |
| **Process Owner / Manager** | Owns a business outcome, not notation | Plain-English summaries, "what's wrong / what could be better", automation & cost insight |
| **Subject-Matter Expert (e.g., operations / domain lead)** | Deep domain, little BPMN | Describe a process in words → get a valid diagram; sanity-check that a diagram matches reality |
| **Developer / Integration Engineer** | Implements the process | Machine-readable BPMN XML, execution-semantics questions, gaps that block automation |
| **New Joiner / Trainee** | Learning BPMN or a specific process | On-demand tutor; narrated walkthrough of existing diagrams |

> **Domain note:** v1 is deliberately **industry-agnostic**. Optional industry/organisation-specific templates and compliance packs are a later-phase extension (§11), not a v1 commitment.

---

## 5. Core Capabilities (Feature Overview)

The three sponsor-requested capabilities, plus a curated set of additional business-value features. Each is detailed in §6.

| # | Capability | Sponsor-requested | In v1 | Priority |
|---|------------|:---:|:---:|:---:|
| C1 | **BPMN Q&A / Tutor** — answer any question about BPMN | ✓ | ✓ | Must |
| C2 | **Schema Generation** — natural language → valid BPMN 2.0 diagram | ✓ | ✓ | Must |
| C3 | **Schema Review & Improvement** — validate + recommend fixes | ✓ | ✓ | Must |
| C4 | **Diagram Explanation** — BPMN file → plain-English narrative | | ✓ | Must |
| C5 | **Best-Practice & Convention Linting** — style/quality checks | | | Should |
| C6 | **Automation-Opportunity Detection** — flag automatable steps | | ✓ | Must |
| C7 | **Compliance & Governance Check** — map process to policy/regulatory needs | | ✓ | Should |
| C8 | **Bottleneck & Efficiency Advisor** — spot delays, rework, over-complexity | | | Could |
| C9 | **RACI & Role Extraction** — derive responsibilities from lanes/pools | | | Could |
| C10 | **Version Diff & Change Explanation** — compare two diagram versions | | | Could |
| C11 | **Process Repository Search** — ask questions across many diagrams | | | Could |
| C12 | **Test-Scenario Generation** — enumerate execution paths / test cases | | | Could |

> **v1 committed scope:** C1, C2, C3, C4, C6, C7. Remaining capabilities are planned for later phases (§11).

---

## 6. Detailed Capability Descriptions

Each capability is written as: *What it does → Example interaction → Inputs/Outputs → Acceptance criteria.*

### 6.1 C1 — BPMN Q&A / Tutor  *(Sponsor goal)*
**What:** Answer any conceptual or how-to question about BPMN 2.0 — elements, symbols, semantics, diagram types, differences between constructs, and best practices.

**Example:**
> *User:* "What's the difference between a Message Event and a Signal Event, and when would I use each?"
> *Assistant:* Explains scope (1-to-1 vs 1-to-many broadcast), throwing/catching variants, and gives a concrete example — with a citation to the relevant BPMN 2.0 spec section.

**Inputs:** free-text question (optionally with a referenced element or diagram).
**Outputs:** grounded answer, with citations to the BPMN 2.0 spec and, where useful, a small illustrative snippet or diagram description.

**Acceptance criteria:**
- Factually correct against BPMN 2.0 for a defined benchmark question set (target ≥ 90% correct — see §10).
- Every substantive claim is traceable to the spec (retrieval-grounded, not hallucinated).
- Answers include an "I'm not certain / not in the standard" path rather than fabricating.

### 6.2 C2 — Schema Generation from Natural Language  *(Sponsor goal)*
**What:** Turn a described process into a **valid, importable BPMN 2.0 file** (`.bpmn` / BPMN XML), not just prose.

**Example:**
> *User:* "A purchase request: an employee submits a request, the finance team reviews it. If the amount is over £5,000, route to manager approval; otherwise auto-approve. Notify the requester in both cases."
> *Assistant:* Produces a BPMN diagram with a start event, employee/finance lanes, an exclusive gateway on amount, two approval paths, and an end event — delivered as valid BPMN XML plus a rendered preview and a plain-English summary of what it built and any assumptions it made.

**Inputs:** natural-language description; optional constraints (participants, systems, required steps).
**Outputs:** BPMN 2.0 XML (schema-valid, layout coordinates included so it renders), preview image, list of assumptions & clarifying questions.

**Acceptance criteria:**
- Output validates against the BPMN 2.0 XSD and imports cleanly into a standard modeller (bpmn.io / Camunda Modeler).
- Structurally sound: exactly one start trigger per path, all elements connected, gateways balanced.
- The Assistant states assumptions and asks clarifying questions when the description is ambiguous.

### 6.3 C3 — Schema Review & Improvement  *(Sponsor goal)*
**What:** Given an existing BPMN file, validate it and return prioritised, actionable improvement recommendations — from hard standard violations to soft quality/readability advice.

**Checks span three tiers:**
1. **Correctness (standard-conformance):** unconnected elements, missing start/end events, deadlock-prone or unbalanced gateways, implicit/ambiguous splits, invalid element combinations.
2. **Clarity/best-practice:** unlabeled tasks/gateways, over-large diagrams that should be decomposed into sub-processes, inconsistent naming, missing error/timeout handling.
3. **Business value:** manual steps that could be automated, redundant approvals, missing exception paths, unclear ownership.

**Example:**
> *User:* uploads `invoice-approval.bpmn`
> *Assistant:* "3 issues found. **High:** the exclusive gateway 'Approved?' has no default flow → risk of a stuck token. **Medium:** two tasks are unlabeled. **Low:** consider a timeout on 'Wait for manager sign-off' (currently no escalation path)." Each with the element ID, why it matters, and a suggested fix.

**Inputs:** BPMN 2.0 file.
**Outputs:** ranked findings (severity, element reference, rationale, recommended fix); optionally an auto-fixed version for the user to accept/reject.

**Acceptance criteria:**
- Detects a defined set of seeded defects with ≥ 90% recall on the validation corpus.
- Findings reference specific element IDs and are individually explained.
- No false "violations" that are actually valid BPMN.

### 6.4 C4 — Diagram Explanation / Narration
**What:** Convert a BPMN file into a clear plain-English narrative — living documentation, onboarding material, or an accessibility aid.
**Outputs:** step-by-step narrative, role summary, decision-point list. Useful for stakeholders who can't read BPMN and for auto-generating process documentation.

### 6.5 C5 — Best-Practice & Convention Linting
**What:** A configurable "linter" for BPMN, checking both the OMG standard and *organisation-specific* conventions (naming rules, mandatory lanes, required annotations). Enables consistency across teams.

### 6.6 C6 — Automation-Opportunity Detection
**What:** Analyse a process and flag steps that are candidates for automation (manual data entry, routing decisions expressible as rules, notifications), with a rough effort/benefit indication. Directly ties BPMN work to operational improvement.

### 6.7 C7 — Compliance & Governance Check
**What:** Check a process against policy/regulatory expectations (e.g., presence of an audit/logging point, a data-handling boundary, a segregation-of-duties or mandatory-approval step). Rules are configurable per organisation/regulation. High value in any regulated or audited setting.

### 6.8 C8 — Bottleneck & Efficiency Advisor
**What:** Identify structural inefficiencies — long serial chains that could be parallelised, repeated rework loops, excessive hand-offs between lanes, over-complex gateways. (Structural analysis in v1; timing analysis if event-log data is later integrated.)

### 6.9 C9 — RACI & Role Extraction
**What:** Derive a RACI-style responsibility matrix from pools/lanes and task assignments, and flag steps with unclear or missing ownership.

### 6.10 C10 — Version Diff & Change Explanation
**What:** Compare two versions of a BPMN diagram and explain what changed *and why it matters* in business terms ("a new approval step was added before payment").

### 6.11 C11 — Process Repository Search (Q&A over many diagrams)
**What:** Ask questions across a whole library of process diagrams: "Which of our processes require manager approval?" or "Where do we send data to a third party?" Turns a folder of `.bpmn` files into a searchable knowledge base.

### 6.12 C12 — Test-Scenario Generation
**What:** Enumerate the distinct execution paths through a process and produce human-readable test scenarios / acceptance cases — useful before automating or handing to developers/QA.

---

## 7. End-to-End User Journeys

**Journey A — Analyst drafts a new process**
1. Analyst describes the process in chat (C2). 2. Assistant generates BPMN + asks 2 clarifying questions. 3. Analyst answers; diagram is refined. 4. Assistant runs review (C3) and lint (C5). 5. Analyst exports the `.bpmn` to their modeller.

**Journey B — Manager improves an existing process**
1. Manager uploads a diagram. 2. Assistant narrates it in plain English (C4). 3. Manager asks "what could be better?" 4. Assistant returns improvement, automation and compliance findings (C3/C6/C7), ranked by impact. 5. Manager exports a report.

**Journey C — New joiner learns**
1. Trainee asks conceptual questions (C1). 2. Uploads a real team diagram and asks the Assistant to walk them through it (C4). 3. Asks "what would happen if the approval is rejected?" (path reasoning, C12).

---

## 8. Functional Requirements Summary

| ID | Requirement | Capability | Priority |
|----|-------------|-----------|:--------:|
| FR-1 | Answer free-text BPMN questions with spec-grounded citations | C1 | Must |
| FR-2 | Generate valid, importable BPMN 2.0 XML from a description | C2 | Must |
| FR-3 | Ask clarifying questions when input is ambiguous | C2 | Must |
| FR-4 | Ingest a BPMN file and validate against the standard | C3 | Must |
| FR-5 | Return ranked, element-referenced improvement recommendations | C3 | Must |
| FR-6 | Produce a plain-English narrative of a diagram | C4 | Must |
| FR-7 | Apply configurable organisational lint rules | C5 | Should |
| FR-8 | Flag automation candidates | C6 | Should |
| FR-9 | Check configurable compliance rules | C7 | Should |
| FR-10 | Maintain conversational context across a session | All | Must |
| FR-11 | Refuse/flag when a question is outside BPMN scope or knowledge | C1 | Must |
| FR-12 | Export findings/diagrams (file + report) | C3/C4 | Should |

---

## 9. Conceptual Architecture (Solution Direction)

*Indicative only — the TDD will finalise choices.*

```
          ┌──────────────────────────────────────────────┐
          │                 User Interface                │
          │        (chat + file upload + preview)         │
          └───────────────────────┬──────────────────────┘
                                   │
          ┌────────────────────────▼─────────────────────┐
          │              Agent / Orchestrator             │
          │  routes intent → selects tools → composes     │
          │  answer; keeps conversation state             │
          └───┬───────────┬───────────┬──────────────┬────┘
              │           │           │              │
     ┌────────▼───┐ ┌─────▼──────┐ ┌──▼───────────┐ ┌▼───────────────┐
     │ Fine-tuned │ │ Retrieval  │ │ BPMN Toolkit │ │ Rule Engines   │
     │ BPMN model │ │ (spec + KB │ │ parse /      │ │ lint /         │
     │ (stages    │ │  = RAG,    │ │ validate /   │ │ compliance /   │
     │  1–3)      │ │  citations)│ │ generate XML │ │ automation     │
     └────────────┘ └────────────┘ └──────────────┘ └────────────────┘
```

**Design principles that follow from the requirements:**
- **Grounding over recall.** The fine-tuned model supplies fluency and BPMN intuition; a **retrieval layer over the BPMN 2.0 spec** supplies verifiable facts and citations (addresses FR-1, FR-11, hallucination risk).
- **Deterministic tools for hard rules.** Validation, XSD checks, gateway/deadlock analysis, and XML generation are handled by **deterministic code / a BPMN library** (e.g., an XSD validator + graph analysis), not left to the model — the model *explains* and *orchestrates*.
- **Agentic layer.** An orchestrator interprets intent, calls the right tool(s), and composes the response — this is the "agent that can answer any human question" the sponsor wants.
- **Self-hosted model, upgraded from the POC.** Deployment is **on-prem / in-tenant only** — no hosted LLM. The POC's `TinyLlama-1.1B` is too small for production reasoning, so the design assumes a **larger open-weight model that can still run self-hosted** (e.g., a 7B–14B-class instruction model), fine-tuned with the existing LoRA/DPO approach for BPMN grounding. Grounding (retrieval) and deterministic tools carry much of the accuracy load, which keeps the self-hosted model's job tractable. This constraint makes the retrieval + tools layers *more* important, not less — they compensate for a smaller-than-hosted model.
- **On-prem infrastructure.** All components (model serving, retrieval index, BPMN toolkit, rule engines, UI) run inside the customer tenant; uploaded diagrams never leave it. See §13.

---

## 10. Success Metrics (KPIs)

| Metric | Target (v1) |
|--------|-------------|
| Q&A accuracy on benchmark question set (C1) | ≥ 90% correct |
| Generated diagrams that pass XSD validation (C2) | ≥ 95% |
| Seeded-defect detection recall (C3) | ≥ 90% |
| False-positive rate on valid diagrams (C3) | ≤ 5% |
| Grounded-answer rate (claims with citations) (C1) | ≥ 95% |
| User task completion without expert help (usability) | Measured via pilot |
| User-rated usefulness (1–5) in pilot | ≥ 4.0 |

A curated **evaluation set** (gold questions, known-good and deliberately-broken BPMN files) must be built alongside development to measure these.

---

## 11. Delivery Roadmap (Phased)

Aligns with, and extends, the existing `readme.md` roadmap.

| Phase | Scope | Delivers |
|-------|-------|----------|
| **P0 — Foundation / POC (done)** | 3-stage LoRA/DPO fine-tuning on TinyLlama-1.1B | BPMN-knowledgeable base model — research baseline only |
| **P1 — Grounded Q&A Agent (v1 start)** | Upgrade to a larger **self-hosted** open model; add retrieval over the spec + agent orchestrator + **standalone chat UI**; expand instruction/DPO data | **C1, C4**, refusal behaviour (FR-11) |
| **P2 — Author & Review (v1)** | BPMN parse / generate / validate toolkit | **C2, C3** |
| **P3 — Business Advisor (v1)** | Rule engines & analysis | **C6, C7** |
| **P4 — Extend** | Linting, bottleneck, RACI, repository search, version diff, test-gen; **modeller plugin**; optional **industry/organisation** templates & compliance packs | C5, C8–C12, plugin delivery, domain specialisation |

> **v1 = P1–P3** (chat app, self-hosted, generic BPMN, capabilities C1–C4/C6/C7). **P4** covers the deferred delivery channel (plugin), domain specialisation, and remaining capabilities.

---

## 12. Data Requirements

- **Expand instruction & preference data** well beyond the current 56/39 rows (target: several hundred diverse, high-quality examples covering all element types, diagram types, and edge cases).
- **Curated BPMN file corpus** — valid diagrams *and* deliberately-flawed ones (with labelled defects) for training/validating C3.
- **Rule libraries** — best-practice lint rules, compliance rule sets (generic; optional domain-specific packs in a later phase).
- **Golden evaluation set** — for the KPIs in §10.
- **Provenance/licensing** — ensure the BPMN spec and any third-party diagrams are cleared for use.

---

## 13. Non-Functional Requirements

| Area | Requirement |
|------|-------------|
| **Accuracy & trust** | Grounded answers with citations; explicit uncertainty; no fabricated spec references |
| **Privacy/security** | Business process diagrams may be commercially sensitive. On-prem / in-tenant deployment; no leakage of uploaded diagrams to third parties |
| **Performance** | Interactive response times for chat; batch mode acceptable for large-repo analysis |
| **Usability** | Usable by non-technical staff; plain language by default, detail on demand |
| **Interoperability** | Consume/produce standard BPMN 2.0 XML compatible with common modellers |
| **Extensibility** | New rules, templates, and domain packs added without retraining the model |
| **Auditability** | Findings and generated artefacts are explainable and exportable |

---

## 14. Assumptions, Risks & Open Questions

**Assumptions**
- BPMN **2.0** is the target standard.
- Input/output interchange format is BPMN 2.0 XML (`.bpmn`).
- The existing TinyLlama fine-tune is a **POC baseline**; production uses a larger **self-hosted** open model with the same LoRA/DPO grounding approach.
- v1 delivery is a **standalone chat app**, deployed **on-prem / in-tenant**, covering **generic, industry-agnostic** BPMN.

**Key risks & mitigations**
| Risk | Mitigation |
|------|-----------|
| Model hallucinates BPMN facts | Retrieval grounding + citations + deterministic validators (§9) |
| **Self-hosted model underperforms on complex reasoning** (no hosted-LLM fallback) | Choose the largest open model the tenant's hardware allows; push hard logic into deterministic tools; lean heavily on retrieval grounding (§9) |
| **On-prem hardware cost / capacity** for a larger model + serving | Right-size the model (7B–14B class); quantise; scope hardware in the TDD |
| Sparse training/eval data | Invest in data expansion & a golden set (§12) |
| Sensitive diagrams leak | On-prem/in-tenant deployment; diagrams never leave the tenant (§13) |
| Scope creep into a full modelling tool | Explicit non-goals (§3.3) |

**Resolved decisions** (sponsor-confirmed, v0.2 — see header)
1. Deployment: **standalone chat app first**, modeller plugin later (P4).
2. Model: **self-hosted / on-prem only**, no hosted LLM.
3. Domain: **generic, industry-agnostic BPMN in v1**; optional domain specialisation in P4.
4. v1 capabilities: **C1–C4, C6, C7**.

**Remaining open questions for the TDD**
1. Which specific open-weight model and what on-prem hardware/serving stack (GPU class, quantisation)?
2. Retrieval stack choice (vector store, embedding model) — must also be self-hostable.
3. BPMN toolkit choice for parse/validate/generate (library vs. custom).
4. Target scale of the training/eval data expansion for v1.

---

## 15. Glossary

| Term | Meaning |
|------|---------|
| **BPMN** | Business Process Model and Notation — OMG standard for graphically modelling business processes |
| **Schema / diagram** | A specific BPMN model (a process drawing), stored as BPMN 2.0 XML |
| **Gateway** | BPMN element controlling flow divergence/convergence (exclusive, parallel, inclusive, etc.) |
| **Pool / Lane** | Participant container / role sub-partition within a participant |
| **RAG** | Retrieval-Augmented Generation — grounding answers in retrieved source text |
| **DPO** | Direct Preference Optimisation — aligning a model to preferred responses |
| **LoRA** | Low-Rank Adaptation — parameter-efficient fine-tuning method |
| **Agent** | An orchestration layer that interprets intent and calls tools/models to fulfil a request |

---

*End of document. This is a living draft — Section 14 open questions should be resolved with the sponsor and folded into v1.0.*
