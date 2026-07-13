#!/usr/bin/env python3
"""
D2 — Dataset coverage report.

Implements the coverage half of deliverable D2 in doc/Training-Data-Build-Spec.md
(§5). Produces a picture of how far the current data is from the v1 targets, on four axes:

  Axis 1 - Capability x volume  (C1..C7 vs targets in spec §5)
  Axis 2 - BPMN element/type coverage by prose mention (spec §5 element list)
  Axis 3 - BPMN 2.0 element INSTANCE coverage (parsed from real diagram XML)
  Axis 4 - C3 anti-pattern / edge-case coverage (defect_type distribution)

Capability is read from meta.capability when present (authoritative). For legacy
rows without meta, a clearly-labelled heuristic estimate is shown so the baseline
is informative even before rows are tagged.

Usage:
    python coverage_report.py <file.jsonl> [<file2.jsonl> ...] [--md OUTFILE]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# v1 SFT volume targets (spec §5, Axis 1).
SFT_TARGETS = {"C1": 300, "C2": 200, "C3": 200, "C4": 150, "C6": 100, "C7": 100}
PREFERENCE_TARGET = 300

# BPMN element/type coverage keywords (spec §5, Axis 2).
ELEMENTS = {
    "startEvent": ["startevent", "start event"],
    "endEvent": ["endevent", "end event"],
    "intermediateEvent": ["intermediate event", "intermediatecatch", "intermediatethrow"],
    "boundaryEvent": ["boundaryevent", "boundary event"],
    "userTask": ["usertask", "user task"],
    "serviceTask": ["servicetask", "service task"],
    "manualTask": ["manualtask", "manual task"],
    "scriptTask": ["scripttask", "script task"],
    "subProcess": ["subprocess", "sub-process", "sub process"],
    "callActivity": ["callactivity", "call activity"],
    "multiInstance": ["multi-instance", "multiinstance", "multi instance"],
    "exclusiveGateway": ["exclusivegateway", "exclusive gateway"],
    "parallelGateway": ["parallelgateway", "parallel gateway"],
    "inclusiveGateway": ["inclusivegateway", "inclusive gateway"],
    "eventBasedGateway": ["eventbasedgateway", "event-based gateway", "event based gateway"],
    "sequenceFlow": ["sequenceflow", "sequence flow"],
    "messageFlow": ["messageflow", "message flow"],
    "defaultFlow": ["default flow", "default sequence flow"],
    "conditionalFlow": ["conditional flow", "conditionalflow"],
    "pool": ["pool"],
    "lane": ["lane"],
    "dataObject": ["dataobject", "data object"],
    "dataStore": ["datastore", "data store"],
    "textAnnotation": ["textannotation", "text annotation", "annotation"],
}

XML_DOC_STARTS = ("<?xml", "<definitions", "<bpmn:definitions", "<bpmn:")
FENCE_RE = re.compile(r"```(?:xml)?\s*(.*?)```", re.DOTALL)

try:
    from lxml import etree
    _HAVE_LXML = True
except Exception:  # pragma: no cover
    _HAVE_LXML = False

# Full BPMN 2.0 element taxonomy for INSTANCE coverage (elements actually present in the
# diagram XML, not just mentioned in prose) — the checklist used by the BPMN-expert audit.
ELEMENT_TAXONOMY = {
    "Events": ["startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
               "boundaryEvent"],
    "Activities": ["task", "userTask", "serviceTask", "sendTask", "receiveTask", "manualTask",
                   "scriptTask", "businessRuleTask", "subProcess", "callActivity",
                   "adHocSubProcess", "transaction"],
    "Gateways": ["exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway",
                 "complexGateway"],
    "Connecting": ["sequenceFlow", "messageFlow", "association"],
    "Swimlanes": ["participant", "lane", "collaboration"],
    "Data": ["dataObject", "dataObjectReference", "dataStore", "dataStoreReference",
             "dataOutputAssociation"],
    "Artifacts": ["textAnnotation", "group"],
    "Loop/MI": ["standardLoopCharacteristics", "multiInstanceLoopCharacteristics"],
}


def _xml_docs_in_row(row):
    docs = []
    for field in ("output", "input", "chosen", "rejected"):
        v = row.get(field)
        if not isinstance(v, str) or "<" not in v:
            continue
        blocks = FENCE_RE.findall(v)
        if blocks:
            docs += [b.strip() for b in blocks if b.strip().startswith(XML_DOC_STARTS)]
        elif v.strip().startswith(XML_DOC_STARTS):
            docs.append(v.strip())
    return docs


def _localnames(xml):
    if not _HAVE_LXML:
        return set()
    try:
        return set(etree.QName(e).localname for e in etree.fromstring(xml.encode("utf-8")).iter())
    except Exception:
        return set()


def row_text(row: dict) -> str:
    parts = []
    for k in ("instruction", "input", "output", "prompt", "chosen", "rejected"):
        v = row.get(k)
        if isinstance(v, str):
            parts.append(v)
    return "\n".join(parts).lower()


def _field_has_xml_doc(val: str) -> bool:
    """True only if the field actually contains an XML document (fenced or leading),
    not merely an inline tag mention in prose."""
    for block in FENCE_RE.findall(val):
        if block.strip().startswith(XML_DOC_STARTS):
            return True
    return val.strip().startswith(XML_DOC_STARTS)


def has_xml(row: dict) -> bool:
    for k in ("input", "output", "chosen", "rejected"):
        v = row.get(k)
        if isinstance(v, str) and _field_has_xml_doc(v):
            return True
    return False


def heuristic_capability(row: dict) -> str:
    """Rough capability guess for untagged legacy rows (clearly labelled as an estimate)."""
    text = (row.get("instruction", "") + " " + row.get("prompt", "")).lower()
    produces_xml = isinstance(row.get("output"), str) and _field_has_xml_doc(row["output"])
    if re.search(r"\bwrite\b.*bpmn|generate a bpmn|generate bpmn", text) or produces_xml:
        return "C2"
    if re.search(r"what is wrong|analyze this|identify.*(error|deadlock|anti-pattern)|critique|improve", text):
        return "C3"
    if re.search(r"explain this diagram|narrate|walk through|describe this", text):
        return "C4"
    return "C1"  # default: conceptual Q&A / tutoring


def analyze(paths: list[Path]):
    sft_meta = Counter()
    sft_heur = Counter()
    pref_count = 0
    untagged = 0
    input_field_used = 0
    xml_rows = 0
    total = 0
    element_hits = Counter()
    element_instances = Counter()   # actual BPMN element localnames found in diagram XML
    antipatterns = Counter()        # C3 defect_type distribution
    per_file = {}

    for p in paths:
        fcount = 0
        with p.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                total += 1
                fcount += 1
                row = json.loads(line)
                meta = row.get("meta") or {}
                is_pref = all(k in row for k in ("prompt", "chosen", "rejected"))
                if is_pref:
                    pref_count += 1
                else:
                    cap = meta.get("capability") if isinstance(meta, dict) else None
                    if cap:
                        sft_meta[cap] += 1
                    else:
                        untagged += 1
                        sft_heur[heuristic_capability(row)] += 1
                    if isinstance(row.get("input"), str) and row["input"].strip():
                        input_field_used += 1
                if has_xml(row):
                    xml_rows += 1
                text = row_text(row)
                for el, kws in ELEMENTS.items():
                    if any(kw in text for kw in kws):
                        element_hits[el] += 1
                # instance-level element coverage (parse real diagram XML)
                for doc in _xml_docs_in_row(row):
                    element_instances.update(_localnames(doc))
                # anti-pattern coverage from C3 rows
                if isinstance(meta, dict) and meta.get("capability") == "C3" and meta.get("defect_type"):
                    antipatterns[meta["defect_type"]] += 1
        per_file[str(p)] = fcount

    return {
        "total": total, "per_file": per_file, "pref_count": pref_count,
        "sft_meta": sft_meta, "sft_heur": sft_heur, "untagged": untagged,
        "input_field_used": input_field_used, "xml_rows": xml_rows,
        "element_hits": element_hits, "element_instances": element_instances,
        "antipatterns": antipatterns,
    }


def render(a: dict) -> str:
    L = []
    L.append("# Dataset Coverage Report (baseline)\n")
    L.append("_Generated by src/data_pipeline/coverage_report.py — see doc/Training-Data-Build-Spec.md §5._\n")
    L.append("## Totals\n")
    for f, c in a["per_file"].items():
        L.append(f"- `{f}`: {c} rows")
    L.append(f"- **Total rows:** {a['total']}")
    L.append(f"- Rows containing BPMN XML: {a['xml_rows']}")
    L.append(f"- SFT rows using the `input` field (needed for C3/C4/C6/C7): {a['input_field_used']}")
    L.append(f"- SFT rows untagged (no meta.capability): {a['untagged']}\n")

    L.append("## Axis 1 — Capability × volume (SFT)\n")
    L.append("| Cap | Tagged (meta) | Heuristic (untagged) | Combined | Target | Gap |")
    L.append("|-----|:-------------:|:--------------------:|:--------:|:------:|:---:|")
    for cap, target in SFT_TARGETS.items():
        tagged = a["sft_meta"].get(cap, 0)
        heur = a["sft_heur"].get(cap, 0)
        combined = tagged + heur
        gap = max(0, target - combined)
        L.append(f"| {cap} | {tagged} | {heur} | {combined} | {target} | {gap} |")
    total_sft = sum(a["sft_meta"].values()) + sum(a["sft_heur"].values())
    total_target = sum(SFT_TARGETS.values())
    L.append(f"| **SFT total** | {sum(a['sft_meta'].values())} | {sum(a['sft_heur'].values())} | "
             f"{total_sft} | {total_target} | {max(0, total_target - total_sft)} |")
    L.append(f"\n**Preference pairs:** {a['pref_count']} / {PREFERENCE_TARGET} target "
             f"(gap {max(0, PREFERENCE_TARGET - a['pref_count'])})\n")
    L.append("> Heuristic counts are an *estimate* for legacy rows lacking `meta.capability`. "
             "Tag rows (D4–D6) to make Axis 1 authoritative.\n")

    L.append("## Axis 2 — BPMN element / type coverage\n")
    L.append("| Element | Rows mentioning it |")
    L.append("|---------|:------------------:|")
    for el in ELEMENTS:
        L.append(f"| {el} | {a['element_hits'].get(el, 0)} |")
    missing = [el for el in ELEMENTS if a["element_hits"].get(el, 0) == 0]
    L.append("")
    if missing:
        L.append(f"**Elements with zero coverage:** {', '.join(missing)}")
    else:
        L.append("**All tracked elements have at least one mention.**")

    # ---- Axis 3: instance-level element coverage (real diagram XML) ----
    inst = a["element_instances"]
    total_el = sum(len(v) for v in ELEMENT_TAXONOMY.values())
    covered_el = sum(1 for v in ELEMENT_TAXONOMY.values() for e in v if inst.get(e, 0) > 0)
    L.append("\n## Axis 3 — BPMN 2.0 element INSTANCE coverage (in diagrams)\n")
    L.append("_Elements actually present in the diagram XML across the scanned datasets "
             "(parsed, not prose-matched). This is the coverage the BPMN-expert audit fixed._\n")
    L.append(f"**{covered_el} / {total_el} element kinds present as real instances.**\n")
    L.append("| Category | Element | Instances | Present |")
    L.append("|----------|---------|:---------:|:-------:|")
    absent = []
    for cat, els in ELEMENT_TAXONOMY.items():
        for e in els:
            n = inst.get(e, 0)
            L.append(f"| {cat} | {e} | {n} | {'yes' if n else '—'} |")
            if not n:
                absent.append(e)
    L.append("")
    if absent:
        L.append(f"**Not instantiated in these datasets:** {', '.join(absent)} "
                 "(note: `dataStore` is rejected by the SpiffWorkflow validation gate as "
                 "'unimplemented', but is present in the MIWG eval set and the C1 knowledge base).")
    else:
        L.append("**Every element kind in the taxonomy is present as a real instance.**")

    # ---- Axis 4: C3 anti-pattern coverage ----
    ap = a["antipatterns"]
    L.append("\n## Axis 4 — C3 anti-pattern / edge-case coverage\n")
    if ap:
        real = {k: v for k, v in ap.items() if k != "none"}
        L.append(f"**{len(real)} anti-pattern types** (plus clean negatives), grounded in BPMN "
                 "soundness and 7PMG taxonomies:\n")
        L.append("| Anti-pattern (defect_type) | Rows |")
        L.append("|-----------------------------|:----:|")
        for k in sorted(ap):
            L.append(f"| {k} | {ap[k]} |")
    else:
        L.append("_No C3 rows in the scanned files._")

    L.append("\n## Enrichment log\n")
    L.append("- **Rich elements added to training** (were previously eval-only): boundary events, "
             "collaborations (pools/lanes/message flows), data objects, multi-instance & loop markers, "
             "script/complex/manual/call/receive tasks, throwing message events, text annotations, groups.")
    L.append("- **Train/eval mismatch fixed** via a disjoint MIWG reference split (`diagram_pools.py`) so "
             "rich real-world diagrams (CC BY 3.0) feed both train and eval.")
    L.append("- **Anti-patterns extended** from 8 → 11: added lack-of-synchronization, start-with-incoming, "
             "and end-with-outgoing (soundness/connectivity).")
    L.append("- **Every diagram is XSD-validated** through the SpiffWorkflow gate before acceptance.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="BPMN dataset coverage report (D2).")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--md", type=Path, help="Also write the report as Markdown to this path")
    args = ap.parse_args()

    for p in args.files:
        if not p.exists():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            return 2

    a = analyze(args.files)
    report = render(a)
    if args.md:  # write the UTF-8 artifact first so console encoding can't block it
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(report, encoding="utf-8")
    # Windows consoles default to cp1252 which cannot encode some Unicode (e.g. arrows);
    # print resiliently rather than crash.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(report)
    if args.md:
        print(f"[written] {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
