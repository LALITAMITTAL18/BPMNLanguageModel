#!/usr/bin/env python3
"""
Model runners for the evaluation harness (Phase A).

A runner is anything with `.generate(prompt: str) -> str`. This keeps the harness
model-agnostic so the same eval sets can be scored against:

  - `null`                     -> returns "" (baseline floor; needs no model/GPU)
  - `hf:<model_id>`            -> local Hugging Face transformers model (self-hosted)
  - `openai:<base_url>:<model>`-> an OpenAI-compatible local server (vLLM / Ollama /
                                  llama.cpp) — the on-prem serving path in the TDD

Heavy deps (transformers, requests) are imported lazily so the harness runs with the
null runner out of the box.
"""
from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a BPMN 2.0 expert assistant. Answer precisely. When asked to generate a "
    "diagram, output valid BPMN 2.0 XML. When asked to review, list concrete issues."
)


class NullRunner:
    """Baseline floor — no model. Establishes the 0-capability reference point."""
    name = "null"

    def generate(self, prompt: str) -> str:
        return ""


class HFRunner:
    """Local Hugging Face transformers model (self-hosted, on-prem)."""
    def __init__(self, model_id: str, max_new_tokens: int = 512):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self.name = f"hf:{model_id}"
        self.max_new_tokens = max_new_tokens
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype="auto",
            device_map="auto" if torch.cuda.is_available() else None)

    def generate(self, prompt: str) -> str:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}]
        try:
            text = self.tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        except Exception:
            text = SYSTEM_PROMPT + "\n\n" + prompt
        inputs = self.tok(text, return_tensors="pt").to(self.model.device)
        out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        return self.tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


class OpenAICompatRunner:
    """OpenAI-compatible chat endpoint (vLLM/Ollama/llama.cpp served locally)."""
    def __init__(self, base_url: str, model: str, max_tokens: int = 512):
        self.name = f"openai:{base_url}:{model}"
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens

    def generate(self, prompt: str) -> str:
        import requests
        r = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={"model": self.model, "max_tokens": self.max_tokens, "temperature": 0,
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user", "content": prompt}]},
            timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def get_runner(spec: str):
    """Build a runner from a spec string. Examples:
       null | hf:Qwen/Qwen3-8B | openai:http://localhost:8000:qwen3-8b
    """
    if spec == "null":
        return NullRunner()
    if spec.startswith("hf:"):
        return HFRunner(spec[len("hf:"):])
    if spec.startswith("openai:"):
        rest = spec[len("openai:"):]
        # split into base_url and model on the LAST colon (base_url contains a colon)
        base_url, model = rest.rsplit(":", 1)
        return OpenAICompatRunner(base_url, model)
    raise ValueError(f"unknown runner spec: {spec!r} (use null | hf:<id> | openai:<url>:<model>)")
