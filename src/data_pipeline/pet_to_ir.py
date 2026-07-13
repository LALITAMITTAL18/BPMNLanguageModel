#!/usr/bin/env python3
"""
D5 — Conservative PET -> IR bootstrap (PET dataset, MIT).

Turns PET's annotated process descriptions (patriziobellan/PET) into C2 seed records
(NL description + IR) for build_c2_dataset.py. PET uses token-level NER (Actor,
Activity, Activity Data, gateways) plus relations (flow, uses, ...). Faithfully
reconstructing arbitrary control flow — especially gateways — is error-prone, and the
spec forbids letting volume beat correctness. So this converter is deliberately
CONSERVATIVE:

  - Only documents with NO gateway annotations are considered.
  - Their 'flow' relations must form a simple linear chain (one source, one sink,
    fan-in/out <= 1); anything branching is skipped.
  - Each activity becomes a task named "<verb phrase> <object phrase>" using the
    activity span and its 'uses' Activity-Data span.

Every produced IR is still put through the full validation loop in build_c2_dataset.py,
so incorrect conversions are dropped rather than shipped. Yield is intentionally small;
that is the safe trade-off. The reconstructed NL is taken verbatim from PET tokens.

Usage:
    python pet_to_ir.py --parquet data/raw/PET/pet.parquet --out data/raw/c2_seeds_pet.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ATTRIBUTION = "PET dataset (patriziobellan/PET), MIT"


def reconstruct_text(tokens) -> str:
    text = " ".join(tokens)
    text = re.sub(r"\s+([.,;:)\]])", r"\1", text)   # no space before closing punctuation
    text = re.sub(r"([(\[])\s+", r"\1", text)        # no space after opening bracket
    return text.strip()


def span_phrase(tokens, ner, start_idx, kind):
    """Collect the B-<kind> token at start_idx plus contiguous I-<kind> tokens."""
    words = [tokens[start_idx]]
    j = start_idx + 1
    while j < len(ner) and ner[j] == f"I-{kind}":
        words.append(tokens[j])
        j += 1
    return " ".join(words)


def head_index(sent_ids, word_ids, s, w):
    for i in range(len(sent_ids)):
        if int(sent_ids[i]) == int(s) and int(word_ids[i]) == int(w):
            return i
    return None


def doc_to_ir(row):
    tokens = list(row["tokens"])
    ner = list(row["ner_tags"])
    sent_ids = list(row["sentence-IDs"])
    word_ids = list(row["tokens-IDs"])

    # conservative: skip anything with a gateway
    if any("Gateway" in t for t in ner):
        return None, "has gateway"

    rel = row["relations"]
    r_src_s = list(rel["source-head-sentence-ID"])
    r_src_w = list(rel["source-head-word-ID"])
    r_tgt_s = list(rel["target-head-sentence-ID"])
    r_tgt_w = list(rel["target-head-word-ID"])
    r_type = list(rel["relation-type"])

    # activity heads -> token index
    act_head_idx = {i for i, t in enumerate(ner) if t == "B-Activity"}
    if len(act_head_idx) < 2:
        return None, "fewer than 2 activities"

    # build 'uses' map: activity head token index -> data phrase
    uses = {}
    for k in range(len(r_type)):
        if r_type[k] == "uses":
            ai = head_index(sent_ids, word_ids, r_src_s[k], r_src_w[k])
            di = head_index(sent_ids, word_ids, r_tgt_s[k], r_tgt_w[k])
            if ai is not None and di is not None and ner[di].startswith(("B-Activity Data", "B-Activity")):
                uses.setdefault(ai, span_phrase(tokens, ner, di, "Activity Data"))

    # flow edges between activity heads
    edges = []
    for k in range(len(r_type)):
        if r_type[k] != "flow":
            continue
        si = head_index(sent_ids, word_ids, r_src_s[k], r_src_w[k])
        ti = head_index(sent_ids, word_ids, r_tgt_s[k], r_tgt_w[k])
        if si in act_head_idx and ti in act_head_idx:
            edges.append((si, ti))
    if not edges:
        return None, "no activity flow edges"

    # require a simple linear chain
    succ, pred = {}, {}
    for s, t in edges:
        succ.setdefault(s, []).append(t)
        pred.setdefault(t, []).append(s)
    if any(len(v) > 1 for v in succ.values()) or any(len(v) > 1 for v in pred.values()):
        return None, "branching flow (not linear)"
    sources = [n for n in act_head_idx if n not in pred]
    sinks = [n for n in act_head_idx if n not in succ]
    if len(sources) != 1 or len(sinks) != 1:
        return None, "not a single-source/single-sink chain"

    # walk the chain
    chain = []
    cur = sources[0]
    seen = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        nxt = succ.get(cur, [])
        cur = nxt[0] if nxt else None
    if len(chain) != len(act_head_idx):
        return None, "chain does not cover all activities"

    # build IR
    def task_name(ai):
        verb = span_phrase(tokens, ner, ai, "Activity")
        obj = uses.get(ai, "")
        name = (verb + (" " + obj if obj else "")).strip()
        return name[:80]

    nodes = [{"id": "start", "type": "startEvent", "name": "Start"}]
    edges_ir = []
    prev = "start"
    for n, ai in enumerate(chain, 1):
        nid = f"a{n}"
        nodes.append({"id": nid, "type": "task", "name": task_name(ai)})
        edges_ir.append({"source": prev, "target": nid})
        prev = nid
    nodes.append({"id": "end", "type": "endEvent", "name": "End"})
    edges_ir.append({"source": prev, "target": "end"})

    ir = {"process_id": "Process_" + re.sub(r"\W+", "_", str(row["document name"])),
          "name": str(row["document name"]), "nodes": nodes, "edges": edges_ir}
    return ir, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Conservative PET -> IR C2 seed bootstrap (D5).")
    ap.add_argument("--parquet", type=Path, default=Path("data/raw/PET/pet.parquet"))
    ap.add_argument("--out", type=Path, default=Path("data/raw/c2_seeds_pet.jsonl"))
    args = ap.parse_args()

    if not args.parquet.exists():
        print(f"ERROR: PET parquet not found: {args.parquet}")
        print("Fetch it from https://huggingface.co/datasets/patriziobellan/PET (MIT).")
        return 2

    import pyarrow.parquet as pq
    df = pq.read_table(str(args.parquet)).to_pandas()

    kept, skipped = [], {}
    for _, row in df.iterrows():
        ir, reason = doc_to_ir(row)
        if ir is None:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        kept.append({
            "instruction": "Generate a BPMN 2.0 diagram for the following process: "
                           + reconstruct_text(list(row["tokens"])),
            "ir": ir,
            "meta": {"source": "PET", "doc": str(row["document name"]), "attribution": ATTRIBUTION},
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"PET documents    : {len(df)}")
    print(f"Converted (chain): {len(kept)} -> {args.out}")
    print("Skipped reasons  :", skipped)
    print("Note: converted IRs still pass through build_c2_dataset.py's validation gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
