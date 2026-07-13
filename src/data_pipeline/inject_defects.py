#!/usr/bin/env python3
"""
D3 — Seeded-defect generator for the C3 (Review & Improvement) evaluation set.

Implements deliverable D3 of doc/Training-Data-Build-Spec.md (§6). It takes valid
BPMN 2.0 diagrams (the license-clean BPMN MIWG reference models, CC BY 3.0) and
programmatically injects a catalogue of known structural defects, each with a
ground-truth label. The result is a scalable, license-clean benchmark for measuring
C3 defect-detection recall/precision (FDD KPI; TDD §9).

Each injected diagram remains well-formed XML (the defects are *structural*, not
syntactic), so a reviewer/model must reason about BPMN semantics — not just parse XML.

Defect catalogue (each applied once per diagram when applicable):
  - unlabeled_task        : strip a task's name           -> "task missing label"
  - disconnected_element  : delete a sequence flow + refs -> downstream node unreachable
  - missing_start_event   : delete the start event        -> process cannot instantiate
  - gateway_type_mismatch : XOR split + AND join          -> deadlock
  - duplicate_id          : reuse an existing element id  -> invalid (non-unique id)

Also emits the unmodified diagram as a "none" (negative) row so false-positive rate
can be measured.

Usage:
    python inject_defects.py --src data/raw/bpmn-miwg-test-suite/Reference \
                             --out data/eval/eval_c3_defects.jsonl
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from lxml import etree

ATTRIBUTION = "BPMN MIWG Test Suite, CC BY 3.0 (https://github.com/bpmn-miwg/bpmn-miwg-test-suite)"
_MIWG_NAME = re.compile(r"^[A-C]\.\d")  # MIWG reference case names like A.2.0, C.9.1
TASK_LOCALNAMES = {"task", "userTask", "serviceTask", "manualTask", "scriptTask",
                   "businessRuleTask", "sendTask", "receiveTask"}

REVIEW_INSTRUCTION = (
    "Review this BPMN 2.0 diagram and identify any structural issues (unreachable "
    "elements, missing start/end events, gateway deadlocks, unlabeled or invalid "
    "elements). If the diagram is structurally correct, say so explicitly."
)


# ---------- namespace / helpers ----------

def model_ns(root) -> str:
    """The BPMN model namespace URI (the one the <definitions> root lives in)."""
    return root.tag.split("}")[0].strip("{")


def q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def localname(el) -> str:
    return etree.QName(el).localname


def find_processes(root, ns):
    return root.findall(q(ns, "process"))


def child_flow_ids(el, ns, kind: str):
    """Return list of (element, flow_id) for <incoming>/<outgoing> children."""
    out = []
    for c in el.findall(q(ns, kind)):
        if c.text:
            out.append((c, c.text.strip()))
    return out


def remove_di_for(root, ns, element_id: str):
    """Remove BPMNShape/BPMNEdge whose bpmnElement references a removed element."""
    for di in list(root.iter()):
        if di.get("bpmnElement") == element_id:
            parent = di.getparent()
            if parent is not None:
                parent.remove(di)


def tasks_in(proc, ns):
    return [e for e in proc if localname(e) in TASK_LOCALNAMES]


def serialize(root) -> str:
    body = etree.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


# ---------- defect injectors ----------
# Each takes (root, ns) on a FRESH copy and returns (defect_type, element_id,
# expected_finding) or None if the defect does not apply to this diagram.

def inject_unlabeled_task(root, ns):
    for proc in find_processes(root, ns):
        for t in tasks_in(proc, ns):
            if t.get("name"):
                tid = t.get("id")
                orig = t.get("name")
                del t.attrib["name"]
                return ("unlabeled_task", tid,
                        f"Issue: the task with id '{tid}' (was \"{orig}\") has no name/label. "
                        f"Every task should carry a descriptive verb-noun label. "
                        f"Fix: add a meaningful name attribute.")
    return None


def inject_disconnected_element(root, ns):
    for proc in find_processes(root, ns):
        flows = proc.findall(q(ns, "sequenceFlow"))
        # Pick a flow whose target is a task (so removing it strands a task).
        for f in flows:
            src, tgt = f.get("sourceRef"), f.get("targetRef")
            fid = f.get("id")
            tgt_el = next((e for e in proc if e.get("id") == tgt), None)
            if tgt_el is None or localname(tgt_el) not in TASK_LOCALNAMES:
                continue
            # remove the flow element
            proc.remove(f)
            # remove the <outgoing> ref on source and <incoming> ref on target
            for holder_id in (src, tgt):
                holder = next((e for e in proc if e.get("id") == holder_id), None)
                if holder is None:
                    continue
                for kind in ("incoming", "outgoing"):
                    for c, val in child_flow_ids(holder, ns, kind):
                        if val == fid:
                            holder.remove(c)
            remove_di_for(root, ns, fid)
            tname = tgt_el.get("name") or tgt
            return ("disconnected_element", tgt,
                    f"Issue: task '{tname}' (id '{tgt}') has lost its incoming sequence "
                    f"flow and is now unreachable — no token can ever arrive at it. "
                    f"Fix: reconnect it into the sequence flow.")
    return None


def inject_missing_start_event(root, ns):
    for proc in find_processes(root, ns):
        se = proc.find(q(ns, "startEvent"))
        if se is None:
            continue
        sid = se.get("id")
        # outgoing flow(s) from the start event
        out_ids = [v for _, v in child_flow_ids(se, ns, "outgoing")]
        proc.remove(se)
        remove_di_for(root, ns, sid)
        for fid in out_ids:
            f = next((e for e in proc.findall(q(ns, "sequenceFlow")) if e.get("id") == fid), None)
            if f is not None:
                tgt = f.get("targetRef")
                proc.remove(f)
                remove_di_for(root, ns, fid)
                holder = next((e for e in proc if e.get("id") == tgt), None)
                if holder is not None:
                    for c, val in child_flow_ids(holder, ns, "incoming"):
                        if val == fid:
                            holder.remove(c)
        return ("missing_start_event", sid,
                "Issue: the process has no start event, so it can never be instantiated. "
                "Fix: add a start event that initiates the process flow.")
    return None


def inject_gateway_type_mismatch(root, ns):
    for proc in find_processes(root, ns):
        has_xor_split = any(
            localname(e) == "exclusiveGateway" and len(e.findall(q(ns, "outgoing"))) > 1
            for e in proc
        )
        if not has_xor_split:
            continue
        for e in proc:
            if localname(e) == "exclusiveGateway" and len(e.findall(q(ns, "incoming"))) > 1:
                gid = e.get("id")
                e.tag = q(ns, "parallelGateway")
                return ("gateway_type_mismatch", gid,
                        f"Issue: gateway '{gid}' is a Parallel (AND) join, but the branches were "
                        f"opened by an Exclusive (XOR) split. The AND-join waits for a token on "
                        f"every incoming branch, yet the XOR-split only ever activates one — the "
                        f"process deadlocks. Fix: use a matching Exclusive gateway to merge.")
    return None


def inject_duplicate_id(root, ns):
    for proc in find_processes(root, ns):
        ts = tasks_in(proc, ns)
        if len(ts) >= 2:
            donor, victim = ts[0], ts[1]
            dup = donor.get("id")
            victim.set("id", dup)
            return ("duplicate_id", dup,
                    f"Issue: the id '{dup}' is used by more than one element. BPMN ids must be "
                    f"unique within the document; duplicates make references ambiguous and the "
                    f"file invalid. Fix: give each element a unique id.")
    return None


def inject_implicit_split(root, ns):
    """bpmnlint 'no-implicit-split': a task with >1 outgoing flow (uncontrolled split)."""
    for proc in find_processes(root, ns):
        tasks = tasks_in(proc, ns)
        for t in tasks:
            if len(t.findall(q(ns, "outgoing"))) == 1:
                others = [o for o in tasks if o.get("id") != t.get("id")]
                if not others:
                    continue
                y = others[-1]
                fid = f"_implicit_{t.get('id')}"
                sf = etree.SubElement(proc, q(ns, "sequenceFlow"))
                sf.set("id", fid); sf.set("sourceRef", t.get("id")); sf.set("targetRef", y.get("id"))
                etree.SubElement(t, q(ns, "outgoing")).text = fid
                etree.SubElement(y, q(ns, "incoming")).text = fid
                return ("implicit_split", t.get("id"),
                        f"Issue: task “{_label_of(t)}” (id '{t.get('id')}') now has two outgoing "
                        f"sequence flows but no gateway. This is an uncontrolled (implicit) split — "
                        f"the routing intent (parallel? exclusive?) is ambiguous. Fix: insert an "
                        f"explicit gateway to control the split.")
    return None


def inject_missing_end_event(root, ns):
    """Soundness (proper completion / option-to-complete): remove all end events."""
    for proc in find_processes(root, ns):
        ends = proc.findall(q(ns, "endEvent"))
        if not ends:
            continue
        removed = None
        for se in list(ends):
            sid = se.get("id")
            removed = removed or sid
            in_ids = [v for _, v in child_flow_ids(se, ns, "incoming")]
            proc.remove(se)
            remove_di_for(root, ns, sid)
            for fid in in_ids:
                f = next((e for e in proc.findall(q(ns, "sequenceFlow")) if e.get("id") == fid), None)
                if f is None:
                    continue
                src = f.get("sourceRef")
                proc.remove(f)
                remove_di_for(root, ns, fid)
                holder = next((e for e in proc if e.get("id") == src), None)
                if holder is not None:
                    for c, val in child_flow_ids(holder, ns, "outgoing"):
                        if val == fid:
                            holder.remove(c)
        return ("missing_end_event", removed,
                "Issue: the process has no end event, so tokens never reach proper completion "
                "(the option-to-complete soundness property is violated). Fix: add an end event "
                "that every path can reach.")
    return None


def inject_multiple_start_events(root, ns):
    """7PMG G3 (one start event): add a second start event."""
    for proc in find_processes(root, ns):
        if not proc.findall(q(ns, "startEvent")):
            continue
        ts = tasks_in(proc, ns)
        if not ts:
            continue
        target = ts[0]
        se = etree.SubElement(proc, q(ns, "startEvent"))
        se.set("id", "_start2"); se.set("name", "Second start")
        fid = "_start2_flow"
        etree.SubElement(se, q(ns, "outgoing")).text = fid
        sf = etree.SubElement(proc, q(ns, "sequenceFlow"))
        sf.set("id", fid); sf.set("sourceRef", "_start2"); sf.set("targetRef", target.get("id"))
        etree.SubElement(target, q(ns, "incoming")).text = fid
        return ("multiple_start_events", "_start2",
                "Issue: the process now has more than one start event, creating ambiguous "
                "instantiation. 7PMG guideline G3 recommends exactly one start event. Fix: "
                "consolidate to a single start, or use an event-based gateway if genuinely "
                "multiple triggers are needed.")
    return None


def inject_lack_of_synchronization(root, ns):
    """Soundness (lack of synchronization / multiple termination): AND-split + XOR-join."""
    for proc in find_processes(root, ns):
        has_and_split = any(localname(e) == "parallelGateway" and len(e.findall(q(ns, "outgoing"))) > 1
                            for e in proc)
        if not has_and_split:
            continue
        for e in proc:
            if localname(e) == "parallelGateway" and len(e.findall(q(ns, "incoming"))) > 1:
                gid = e.get("id")
                e.tag = q(ns, "exclusiveGateway")
                return ("lack_of_synchronization", gid,
                        f"Issue: gateway '{gid}' is an Exclusive (XOR) join, but the branches were "
                        f"opened by a Parallel (AND) split. The XOR-join lets each arriving token "
                        f"pass through independently, so the downstream flow runs once per branch — "
                        f"a lack of synchronization causing multiple/uncontrolled completion. Fix: "
                        f"use a Parallel gateway to synchronise the branches.")
    return None


def inject_start_with_incoming(root, ns):
    """Connectivity violation: a start event must not have an incoming sequence flow."""
    for proc in find_processes(root, ns):
        se = proc.find(q(ns, "startEvent"))
        ts = tasks_in(proc, ns)
        if se is None or not ts:
            continue
        src = ts[-1]
        fid = "_bad_start_incoming"
        sf = etree.SubElement(proc, q(ns, "sequenceFlow"))
        sf.set("id", fid); sf.set("sourceRef", src.get("id")); sf.set("targetRef", se.get("id"))
        etree.SubElement(src, q(ns, "outgoing")).text = fid
        etree.SubElement(se, q(ns, "incoming")).text = fid
        return ("start_with_incoming", se.get("id"),
                f"Issue: the start event '{se.get('id')}' has an incoming sequence flow, which is "
                f"invalid — a start event is a source and must have no incoming flow. Fix: remove "
                f"the incoming flow, or replace the start event with an intermediate catch event.")
    return None


def inject_end_with_outgoing(root, ns):
    """Connectivity violation: an end event must not have an outgoing sequence flow."""
    for proc in find_processes(root, ns):
        ee = proc.find(q(ns, "endEvent"))
        ts = tasks_in(proc, ns)
        if ee is None or not ts:
            continue
        tgt = ts[0]
        fid = "_bad_end_outgoing"
        sf = etree.SubElement(proc, q(ns, "sequenceFlow"))
        sf.set("id", fid); sf.set("sourceRef", ee.get("id")); sf.set("targetRef", tgt.get("id"))
        etree.SubElement(ee, q(ns, "outgoing")).text = fid
        etree.SubElement(tgt, q(ns, "incoming")).text = fid
        return ("end_with_outgoing", ee.get("id"),
                f"Issue: the end event '{ee.get('id')}' has an outgoing sequence flow, which is "
                f"invalid — an end event is a sink and must have no outgoing flow. Fix: remove the "
                f"outgoing flow, or replace the end event with an intermediate throw event.")
    return None


def _label_of(el):
    return el.get("name") or el.get("id")


INJECTORS = [
    inject_unlabeled_task,
    inject_disconnected_element,
    inject_missing_start_event,
    inject_missing_end_event,
    inject_gateway_type_mismatch,
    inject_lack_of_synchronization,
    inject_implicit_split,
    inject_multiple_start_events,
    inject_start_with_incoming,
    inject_end_with_outgoing,
    inject_duplicate_id,
]


# ---------- driver ----------

def _clean_output():
    return ("No structural issues found. The process is well-formed: it has a start event, "
            "connected sequence flow, matching gateways, and reaches an end event.")


def _cap_per_type(rows, cap):
    """Keep at most `cap` rows per defect_type, evenly sampled to spread across diagrams/domains."""
    from collections import defaultdict
    buckets = defaultdict(list)
    for r in rows:
        buckets[r["meta"]["defect_type"]].append(r)
    kept = []
    for dtype, items in buckets.items():
        if len(items) <= cap:
            kept.extend(items)
        else:
            stride = len(items) / cap
            kept.extend(items[int(i * stride)] for i in range(cap))
    # renumber ids to stay sequential and unique
    for i, r in enumerate(kept, 1):
        prefix = r["meta"]["id"].split("-")[0]
        r["meta"]["id"] = f"{prefix}-{i:04d}"
    return kept


def _provenance(name, default_tag):
    """Per-diagram source/attribution — MIWG cases are detected by their case-id names."""
    if _MIWG_NAME.match(str(name)):
        return "miwg-reference", ATTRIBUTION
    return default_tag, None


def build_rows(diagrams, split, is_eval, source_tag):
    """diagrams: list of (name, xml_string). Returns C3 rows (clean + injected)."""
    rows = []
    counter = 0
    id_prefix = "c3eval" if is_eval else "c3"
    for name, xml in diagrams:
        try:
            orig_root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
        except etree.XMLSyntaxError:
            continue
        ns = model_ns(orig_root)
        src, attr = _provenance(name, source_tag)

        counter += 1
        meta = {"capability": "C3", "defect_type": "none", "defect_element_id": None,
                "source_diagram": name, "source": src, "split": split,
                "id": f"{id_prefix}-{counter:04d}"}
        if is_eval:
            meta["is_eval"] = True
        if attr:
            meta["attribution"] = attr
        rows.append({"instruction": REVIEW_INSTRUCTION,
                     "input": serialize(copy.deepcopy(orig_root)), "output": _clean_output(),
                     "meta": dict(meta)})

        for inj in INJECTORS:
            root = copy.deepcopy(orig_root)
            result = inj(root, ns)
            if result is None:
                continue
            defect_type, element_id, expected = result
            counter += 1
            dmeta = {"capability": "C3", "defect_type": defect_type, "defect_element_id": element_id,
                     "source_diagram": name, "source": src + "+injected", "split": split,
                     "id": f"{id_prefix}-{counter:04d}"}
            if is_eval:
                dmeta["is_eval"] = True
            if attr:
                dmeta["attribution"] = attr
            rows.append({"instruction": REVIEW_INSTRUCTION, "input": serialize(root),
                         "output": expected, "meta": dmeta})
    return rows


def _load_dir(src_dir: Path):
    out = []
    for p in sorted(src_dir.glob("*.bpmn")):
        out.append((p.stem, p.read_text(encoding="utf-8", errors="replace")))
    return out


def _load_jsonl(path: Path):
    out = []
    for i, line in enumerate(path.open(encoding="utf-8"), 1):
        if line.strip():
            r = json.loads(line)
            out.append((r.get("meta", {}).get("id", f"row{i}"), r["output"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate C3 seeded-defect rows (D3 eval / D6 train).")
    ap.add_argument("--src", type=Path, default=Path("data/raw/bpmn-miwg-test-suite/Reference"),
                    help="Directory of valid .bpmn diagrams")
    ap.add_argument("--from-jsonl", type=Path, default=None,
                    help="Instead of --src, read valid diagrams from the 'output' field of a JSONL (e.g. C2 rows)")
    ap.add_argument("--out", type=Path, default=Path("data/eval/eval_c3_defects.jsonl"))
    ap.add_argument("--split", choices=["train", "test"], default=None)
    ap.add_argument("--cap-per-type", type=int, default=None,
                    help="Keep at most N rows per defect_type (balanced, evenly sampled). Recommended for train.")
    ap.add_argument("--include-miwg-train", action="store_true",
                    help="Also inject defects into the MIWG train-split diagrams (adds rich real-world "
                         "structures — boundary events, pools, data, message flows — to C3 training).")
    args = ap.parse_args()

    if args.from_jsonl:
        if not args.from_jsonl.exists():
            print(f"ERROR: jsonl not found: {args.from_jsonl}")
            return 2
        diagrams = _load_jsonl(args.from_jsonl)
        split = args.split or "train"
        source_tag = "c2-generated"
        if args.include_miwg_train:
            # add rich real-world diagrams (boundary events, pools, data, message flows)
            # to the C3 TRAIN pool so defects are injected into advanced structures too.
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from diagram_pools import miwg_reference_split
            mt, _ = miwg_reference_split(Path("data/raw/bpmn-miwg-test-suite/Reference"))
            diagrams += mt
    else:
        if not args.src.is_dir():
            print(f"ERROR: source dir not found: {args.src}")
            return 2
        split = args.split or "test"
        source_tag = "miwg-reference"
        # For the MIWG eval set, use ONLY the eval split so it stays disjoint from the
        # MIWG cases used in C3 training (--include-miwg-train). Non-MIWG dirs use all files.
        if args.src.resolve() == Path("data/raw/bpmn-miwg-test-suite/Reference").resolve():
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from diagram_pools import miwg_reference_split
            _, diagrams = miwg_reference_split(args.src)
        else:
            diagrams = _load_dir(args.src)

    is_eval = (split == "test")
    rows = build_rows(diagrams, split, is_eval, source_tag)
    if args.cap_per_type:
        rows = _cap_per_type(rows, args.cap_per_type)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    by_type = Counter(r["meta"]["defect_type"] for r in rows)
    print(f"Source diagrams : {len(diagrams)}  (split={split})")
    print(f"Rows written    : {len(rows)} -> {args.out}")
    print("By defect type  :")
    for k, v in sorted(by_type.items()):
        print(f"   {k:24s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
