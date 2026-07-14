#!/usr/bin/env python3
"""
Per-capability evaluation metrics (Phase A), mapped to TDD §9.

Two tiers:
  OBJECTIVE (structural, trustworthy):
    - C2  -> % of generated outputs that are well-formed AND pass the BPMN 2.0 XSD gate
    - C3  -> defect-detection recall (did the review name the injected defect?) and
             false-positive rate on clean diagrams
    - C7  -> agreement with the deterministic per-rule verdicts (does the review flag the
             rules the checker says fail?)
  PROXY (lexical overlap vs the gold reference; a stand-in until an LLM-judge/RAGAS is
  wired, which TDD §9 names as the real metric):
    - C1, C4, C6  -> token-F1 against the reference answer

Each metric function takes (row, prediction) and returns a dict with at least
{"score": float in [0,1]} plus per-metric detail. The harness averages `score`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data_pipeline"))
from bpmn_validate import wellformed, schema_valid, spiff_available  # noqa: E402

XML_DOC_STARTS = ("<?xml", "<definitions", "<bpmn:definitions", "<bpmn:")
FENCE_RE = re.compile(r"```(?:xml)?\s*(.*?)```", re.DOTALL)
_WORD = re.compile(r"[a-z0-9]+")


def _tokens(s: str):
    return _WORD.findall((s or "").lower())


def token_f1(pred: str, ref: str) -> float:
    """Bag-of-words F1 — a rough proxy for answer overlap (not a semantic judge)."""
    p, r = _tokens(pred), _tokens(ref)
    if not p and not r:
        return 1.0
    if not p or not r:
        return 0.0
    from collections import Counter
    pc, rc = Counter(p), Counter(r)
    overlap = sum((pc & rc).values())
    if overlap == 0:
        return 0.0
    prec, rec = overlap / len(p), overlap / len(r)
    return 2 * prec * rec / (prec + rec)


def extract_xml(text: str):
    """Pull a BPMN XML document out of a model response (fenced or leading)."""
    for block in FENCE_RE.findall(text or ""):
        s = block.strip()
        if s.startswith(XML_DOC_STARTS):
            return s
    s = (text or "").strip()
    return s if s.startswith(XML_DOC_STARTS) else None


# ---- OBJECTIVE ----

def metric_c2(row, pred):
    """C2: is the generated diagram a valid, importable BPMN 2.0 document?"""
    xml = extract_xml(pred)
    if xml is None:
        return {"score": 0.0, "wellformed": False, "xsd_valid": False, "note": "no XML in output"}
    wf, _ = wellformed(xml)
    sc, why = schema_valid(xml) if wf else (False, "not well-formed")
    return {"score": 1.0 if (wf and sc is True) else (0.5 if wf else 0.0),
            "wellformed": wf, "xsd_valid": (sc is True),
            "schema_checked": spiff_available(), "note": (why or "")}


# keywords a correct C3 review should surface, per injected defect_type
C3_KEYWORDS = {
    "unlabeled_task": ["label", "name", "unnamed", "unlabel"],
    "disconnected_element": ["unreachable", "disconnect", "no incoming", "not connected", "orphan"],
    "missing_start_event": ["start event", "no start", "instantiat", "cannot start"],
    "missing_end_event": ["end event", "no end", "never ends", "no proper end"],
    "gateway_type_mismatch": ["deadlock", "synchroni", "and-join", "parallel join", "xor split", "stuck"],
    "lack_of_synchronization": ["synchroni", "multiple token", "uncontrolled", "lack of sync", "multiple completion"],
    "implicit_split": ["implicit", "multiple outgoing", "two outgoing", "uncontrolled split"],
    "multiple_start_events": ["multiple start", "more than one start", "several start", "two start"],
    "start_with_incoming": ["start", "incoming"],
    "end_with_outgoing": ["end", "outgoing"],
    "duplicate_id": ["duplicate", "unique", "same id", "id is used"],
}
_ISSUE_WORDS = ["issue", "problem", "error", "invalid", "deadlock", "missing", "unreachable",
                "duplicate", "not connected", "incorrect", "wrong"]
# affirmations that the diagram is fine — must be checked first so "no issues found"
# is not mistaken for an issue report (negation handling).
_CLEAN_PHRASES = ["no issue", "no issues", "no structural issue", "no problem", "no defect",
                  "no error", "no gaps", "well-formed", "is correct", "looks correct",
                  "none found", "no changes needed"]


def metric_c3(row, pred):
    """C3: did the review detect the injected defect (and not cry wolf on clean diagrams)?"""
    dt = (row.get("meta") or {}).get("defect_type")
    low = (pred or "").lower()
    if dt == "none":
        says_clean = any(p in low for p in _CLEAN_PHRASES)
        flagged = (not says_clean) and any(w in low for w in _ISSUE_WORDS)
        return {"score": 0.0 if flagged else 1.0, "kind": "clean",
                "false_positive": flagged}
    kws = C3_KEYWORDS.get(dt, [])
    eid = (row.get("meta") or {}).get("defect_element_id") or ""
    detected = any(k in low for k in kws) or (eid and eid.lower() in low)
    return {"score": 1.0 if detected else 0.0, "kind": "defect",
            "defect_type": dt, "detected": bool(detected)}


def metric_c7(row, pred):
    """C7: does the review flag the rules the deterministic checker says FAIL?"""
    results = (row.get("meta") or {}).get("results") or []
    fails = [r for r in results if not r.get("passed")]
    if not fails:
        return {"score": token_f1(pred, row.get("output", "")), "kind": "compliant",
                "note": "no failing rules; proxy score"}
    low = (pred or "").lower()
    hit = 0
    for r in fails:
        # a rule is 'covered' if the model mentions a distinctive word from its description
        words = [w for w in _tokens(r.get("desc", "")) if len(w) > 4][:4]
        if any(w in low for w in words):
            hit += 1
    return {"score": hit / len(fails), "kind": "gaps", "flagged": hit, "expected": len(fails)}


# ---- PROXY (lexical; LLM-judge/RAGAS is the intended real metric, TDD §9) ----

def metric_proxy(row, pred):
    return {"score": token_f1(pred, row.get("output", "")), "proxy": "token_f1"}


METRICS = {
    "C1": ("proxy (token-F1 vs gold; LLM-judge is the real metric)", metric_proxy),
    "C2": ("objective (XSD-valid rate)", metric_c2),
    "C3": ("objective (defect recall / FP rate)", metric_c3),
    "C4": ("proxy (token-F1 vs gold narrative)", metric_proxy),
    "C6": ("proxy (token-F1 vs gold findings)", metric_proxy),
    "C7": ("objective (failing-rule agreement)", metric_c7),
}
