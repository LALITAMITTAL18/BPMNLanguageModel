# CLAUDE.md — Project Instructions for Coding Agents

This file governs how any AI coding agent (Claude Code or otherwise) must work in this repository. Read it fully before acting on any request.

## 1. The Functional Design Document is FROZEN

- The single source of truth for **what** this product does is:
  [`doc/Functional-Design-Document.md`](doc/Functional-Design-Document.md)
- **This file will never change.** Do **not** edit, reword, restructure, extend, or "improve" it — not even typo fixes — unless the user gives an explicit, unmistakable instruction such as *"edit the Functional Design Document"*. A general request to change behaviour is **not** such an instruction.
- Treat the FDD as a locked contract. It defines the scope, capabilities (C1–C12), v1 commitment, personas, requirements (FR-1…FR-12), KPIs, roadmap, and the confirmed sponsor decisions.

## 2. Every request must be verified against the FDD first

Before starting **any** task, follow this gate:

1. **Locate** the relevant capability (C#) and/or functional requirement (FR-#) in the FDD.
2. **If the request matches** an in-scope requirement → proceed, and reference the C#/FR-# you are fulfilling.
3. **If the request is out of scope, contradicts, or is not covered** by the FDD → **stop and tell the user**. Do not silently implement it. Explain the mismatch and ask whether they want to:
   - (a) proceed anyway as an explicit, documented exception, or
   - (b) first amend the FDD (which requires the explicit instruction described in §1).
4. **If the request is ambiguous** about which requirement it serves → ask the user to confirm the mapping before coding.

> Rule of thumb: *No FDD requirement, no code.* If you cannot point to the part of the FDD a task satisfies, raise it rather than assume.

## 3. Confirmed decisions you must not violate

These are locked in the FDD header and §3.3/§9 and must be honoured in all technical work:

- **Deployment:** standalone chat app first; modeller plugin is a later phase (P4).
- **Model:** **self-hosted / on-prem only.** No third-party hosted LLM APIs, ever, for production paths. Process data must never leave the tenant.
- **Domain:** generic, industry-agnostic BPMN in v1. No industry-specific specialisation in v1.
- **v1 capability scope:** C1, C2, C3, C4, C6, C7. Anything outside this set is later-phase.
- **Standard:** BPMN **2.0**, interchange as BPMN 2.0 XML (`.bpmn`).

## 4. Working conventions

- The **Technical Design Document** (`doc/Technical-Design-Document.md`) specifies *how* to build; it must stay consistent with the FDD. If a technical constraint forces a conflict with the FDD, surface it to the user rather than diverging.
- Prefer changes that trace cleanly to a C#/FR-#. Note the mapping in commit messages and PR descriptions.
- Keep the on-prem / data-privacy constraint in mind for every dependency, model, and service you introduce.

## 5. Project structure (orientation)

- `doc/` — design documents (FDD is frozen; TDD is the living build spec).
- `data/` — BPMN 2.0 spec PDF and training/eval datasets.
- `*.ipynb` — the P0 POC pipeline (domain adaptation → instruction tuning → DPO → evaluation).
- `bpmn_env/` — local Python virtual environment (not part of the product source).
