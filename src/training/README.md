# src/training — Fine-tuning pipeline (Phases B–D)

Trains a self-hostable model on the BPMN datasets via **QLoRA SFT → DPO** (TDD §8).
Designed to run on **Kaggle free GPU** (T4 16 GB) since local hardware is limited.

## Files
| File | Runs on | Purpose |
|------|---------|---------|
| `prepare_data.py` | CPU (local) | Converts `data/instruction/*` → SFT chat format and `data/preference/*` → DPO format; writes `data/training/{sft,dpo}_{train,val}.jsonl` with a held-out val split. |
| `kaggle_train_bpmn.ipynb` | Kaggle GPU | QLoRA SFT then DPO on **Qwen3-8B** (Apache-2.0); saves downloadable LoRA adapters. |
| `requirements.txt` | Kaggle GPU | Training deps (the notebook installs these). |

## Workflow
```
1. LOCAL:   python src/training/prepare_data.py
            -> data/training/*.jsonl  (SFT + DPO, chat/preference format)

2. KAGGLE:  upload data/training/ as a Kaggle Dataset  (e.g. "bpmn-training-data")
            open kaggle_train_bpmn.ipynb, set DATA_DIR, GPU + Internet ON, Run All
            -> bpmn-sft-adapter.zip, bpmn-dpo-adapter.zip  (LoRA adapters, small)

3. LOCAL:   download bpmn-dpo-adapter.zip -> unzip into models/  (git-ignored)

4. EVAL:    score the fine-tuned model with src/eval/run_eval.py and compare to the
            baseline scorecard to measure lift.
```

## Why this setup
- **QLoRA (4-bit)** so an 8B model trains in 16 GB VRAM (TDD §3.3 / §8).
- **Two stages**: SFT teaches the capabilities (C1–C4, C6, C7); DPO aligns toward the
  preferred answers (the `preference/*` pairs).
- **Adapters, not merged weights**, are the download artifact (tens–hundreds of MB vs
  ~16 GB), so they commit/transfer easily. Merge only when standing up a serving endpoint.
- **Model choice**: Qwen3-8B by default (Apache-2.0, self-hostable). Scale to Qwen3-14B on
  bigger GPUs, or drop to Qwen2.5-3B if memory is tight — all configurable in the notebook.

## Notes
- `data/training/` is derived from `data/instruction|preference` — regenerate it with
  `prepare_data.py` whenever those change (then re-upload to Kaggle).
- The frozen `data/eval/*` sets are **not** used in training; they belong to `src/eval/`.

## Correctness fixes applied (verified against current TRL, 2025–2026)
The notebook was reviewed via deep research and corrected for these — get them wrong and the
run silently produces a broken model:
- **`SFTConfig(max_length=...)`, not `max_seq_length`** — the latter is removed in modern TRL;
  its old 1024 default would silently truncate long BPMN XML. Set `MAX_LEN=2048`; cell 3 prints
  a token-length report so you can confirm nothing is truncated.
- **Qwen3 `enable_thinking=False`** on every `apply_chat_template` call — otherwise the default
  template injects `<think>` tags into the BPMN targets/prompts and corrupts training.
- **`processing_class=` (not `tokenizer=`)** — renamed in TRL 0.12, removed by 0.16.
- **QLoRA + gradient checkpointing**: `use_gradient_checkpointing=True` in
  `prepare_model_for_kbit_training`, `gradient_checkpointing_kwargs={"use_reentrant": False}`,
  and `model.enable_input_require_grads()` — required to avoid a no-grad error.
- **DPO**: `ref_model=None` is correct (PEFT uses the adapter-disabled base as reference);
  LoRA rates SFT `2e-4` / DPO `5e-6`, `beta=0.1`, 1 DPO epoch on the small preference set.
- **Optional**: `assistant_only_loss=True` (completion-only) improves instruction-following, but
  only if `MAX_LEN` exceeds every example — with truncation it can silently zero the loss
  (TRL #3927). Use the cell-3 length report before enabling it.
- **T4 note**: no bf16 (use fp16), no flash-attention (SM75). Pin `trl>=0.20`.
