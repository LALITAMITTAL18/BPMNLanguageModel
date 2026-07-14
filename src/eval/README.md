# src/eval — Evaluation harness (Phase A)

Runs the frozen eval sets in `data/eval/` through a model and produces a per-capability
scorecard. This is the **baseline-and-lift** tool: run it against an un-tuned model to get
the baseline, then re-run after SFT/DPO to measure improvement. Metrics map to TDD §9.

## Files
| File | Purpose |
|------|---------|
| `runners.py` | Model runners (`null`, `hf:<id>`, `openai:<url>:<model>`) — pluggable so the harness is model-agnostic and self-hostable. |
| `metrics.py` | Per-capability metrics. Objective for C2/C3/C7; lexical proxy for C1/C4/C6. |
| `run_eval.py` | Orchestrator: load eval sets → generate → score → write Markdown + JSON scorecard. |

## Usage
```bash
# Baseline floor — no model / GPU needed (sanity-checks the harness):
python src/eval/run_eval.py --runner null

# Self-hosted Hugging Face model (needs torch + transformers + weights):
python src/eval/run_eval.py --runner hf:Qwen/Qwen3-8B --limit 20

# On-prem OpenAI-compatible server (vLLM / Ollama / llama.cpp):
python src/eval/run_eval.py --runner openai:http://localhost:8000:qwen3-8b \
    --md doc/reports/eval-qwen3-8b.md --json doc/reports/eval-qwen3-8b.json
```
`--limit N` caps rows per set for quick smoke runs. Output defaults to
`doc/reports/eval-baseline.md`.

## Metrics (TDD §9)
| Cap | Type | What it measures |
|-----|------|------------------|
| C1 | proxy | token-F1 vs gold answer *(LLM-judge / RAGAS is the intended real metric)* |
| **C2** | **objective** | % of generated diagrams that are well-formed **and** pass the BPMN 2.0 XSD gate |
| **C3** | **objective** | defect-detection **recall** on seeded defects + **false-positive rate** on clean diagrams |
| C4 | proxy | token-F1 vs gold narrative |
| C6 | proxy | token-F1 vs gold findings |
| **C7** | **objective** | agreement with the deterministic checker's failing rules |

## Validation
The metrics were sanity-checked with an **oracle** (feeding each row's gold answer as the
prediction): C1/C2/C4/C6/C7 → 1.000, C3 → 1.000 (100% recall, 0% FP). This confirms the
harness measures real signal, not noise. The `null` runner scores ~0 (the expected floor).

## Next
- Wire an **LLM-judge / RAGAS** metric to replace the C1/C4/C6 lexical proxies (TDD §9).
- Stand up a self-hosted model (spike S2) and record the **baseline** scorecard, then compare
  after each training stage (SFT → DPO).
