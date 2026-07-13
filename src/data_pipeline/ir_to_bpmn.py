#!/usr/bin/env python3
"""
Deterministic Intermediate-Representation -> BPMN 2.0 XML builder (TDD §4.5).

The model is trained to emit a compact IR (a JSON node/edge graph); this module is
the deterministic transform that turns that IR into valid, importable BPMN 2.0 XML
with a simple diagram-interchange (DI) layout so it renders. It is used both to build
C2 training data (build_c2_dataset.py) and, at inference time, to convert model output
to XML. Keeping this transform deterministic is what lets the model reason in the
lightweight IR while XML stays the validated interchange artifact.

IR schema (JSON):
{
  "process_id": "Process_1",              # optional; auto-generated if absent
  "name": "Order handling",               # optional
  "nodes": [
     {"id": "start", "type": "startEvent", "name": "Order received"},
     {"id": "t1",    "type": "task",       "name": "Check stock", "taskType": "userTask"},
     {"id": "g1",    "type": "exclusiveGateway", "name": "In stock?"},
     {"id": "end",   "type": "endEvent",   "name": "Done"}
  ],
  "edges": [
     {"source": "start", "target": "t1"},
     {"source": "t1", "target": "g1"},
     {"source": "g1", "target": "end", "name": "yes", "condition": "in_stock == true"}
  ]
}

Supported node types: startEvent, endEvent, task (+ optional taskType: userTask/
serviceTask/manualTask/scriptTask/sendTask/receiveTask/businessRuleTask),
exclusiveGateway, parallelGateway, inclusiveGateway, intermediateCatchEvent,
intermediateThrowEvent, subProcess.
"""
from __future__ import annotations

from lxml import etree

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
DC = "http://www.omg.org/spec/DD/20100524/DC"
DI = "http://www.omg.org/spec/DD/20100524/DI"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
NSMAP = {"bpmn": BPMN, "bpmndi": BPMNDI, "dc": DC, "di": DI, "xsi": XSI}

EVENT_TYPES = {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
               "boundaryEvent"}
EVENT_DEF_TAG = {"timer": "timerEventDefinition", "message": "messageEventDefinition",
                 "error": "errorEventDefinition", "escalation": "escalationEventDefinition",
                 "signal": "signalEventDefinition", "conditional": "conditionalEventDefinition"}
GATEWAY_TYPES = {"exclusiveGateway", "parallelGateway", "inclusiveGateway",
                 "eventBasedGateway", "complexGateway"}
TASK_TYPES = {"task", "userTask", "serviceTask", "manualTask", "scriptTask",
              "sendTask", "receiveTask", "businessRuleTask", "subProcess", "callActivity",
              "transaction", "adHocSubProcess"}


class IRError(ValueError):
    """Raised when the IR is structurally inconsistent (bad references, etc.)."""


def _q(ns, name):
    return f"{{{ns}}}{name}"


def _validate_ir(ir: dict):
    nodes = {n["id"]: n for n in ir.get("nodes", [])}
    if not nodes:
        raise IRError("IR has no nodes")
    for e in ir.get("edges", []):
        if e["source"] not in nodes:
            raise IRError(f"edge source '{e['source']}' is not a node")
        if e["target"] not in nodes:
            raise IRError(f"edge target '{e['target']}' is not a node")
    return nodes


def _element_tag(node_type: str) -> str:
    """Resolve an IR node 'type' to a BPMN element localname."""
    if node_type in EVENT_TYPES or node_type in GATEWAY_TYPES:
        return node_type
    if node_type in TASK_TYPES:
        return node_type  # task/userTask/... are all valid BPMN element names
    raise IRError(f"unsupported node type: {node_type}")


def _layout(nodes: dict, edges: list):
    """Very simple left-to-right layered layout for DI coordinates.

    Rank = longest path from any start node (BFS over edges). Nodes sharing a rank are
    stacked vertically. Good enough to render; exact aesthetics are not validated.
    """
    succ = {nid: [] for nid in nodes}
    indeg = {nid: 0 for nid in nodes}
    for e in edges:
        succ[e["source"]].append(e["target"])
        indeg[e["target"]] += 1
    # ranks via longest-path (Kahn-style relaxation)
    rank = {nid: 0 for nid in nodes}
    from collections import deque
    q = deque([n for n in nodes if indeg[n] == 0]) or deque(list(nodes)[:1])
    seen = set()
    order = []
    tmp_indeg = dict(indeg)
    while q:
        n = q.popleft()
        if n in seen:
            continue
        seen.add(n)
        order.append(n)
        for m in succ[n]:
            rank[m] = max(rank[m], rank[n] + 1)
            tmp_indeg[m] -= 1
            if tmp_indeg[m] <= 0:
                q.append(m)
    # any nodes not reached (cycles) get placed after
    for n in nodes:
        if n not in seen:
            order.append(n)
    # assign coordinates
    per_rank = {}
    pos = {}
    for n in order:
        r = rank[n]
        idx = per_rank.get(r, 0)
        per_rank[r] = idx + 1
        x = 160 + r * 150
        y = 100 + idx * 120
        pos[n] = (x, y)
    return pos


def _shape_size(node_type: str):
    if node_type in EVENT_TYPES:
        return 36, 36
    if node_type in GATEWAY_TYPES:
        return 50, 50
    return 100, 80  # tasks / sub-processes


def _emit_flow(proc, nodes, edges):
    """Emit flow nodes (with markers/events/data assoc) and sequence flows into a process."""
    incoming = {nid: [] for nid in nodes}
    outgoing = {nid: [] for nid in nodes}
    for i, e in enumerate(edges, start=1):
        fid = e.get("id", f"{proc.get('id')}_Flow_{i}")
        e["_id"] = fid
        outgoing[e["source"]].append(fid)
        incoming[e["target"]].append(fid)
    for nid, node in nodes.items():
        el = etree.SubElement(proc, _q(BPMN, _element_tag(node["type"])))
        el.set("id", nid)
        if node.get("name"):
            el.set("name", node["name"])
        if node["type"] == "boundaryEvent":
            if node.get("attachedTo"):
                el.set("attachedToRef", node["attachedTo"])
            el.set("cancelActivity", "true" if node.get("cancelActivity", True) else "false")
        for fid in incoming[nid]:
            etree.SubElement(el, _q(BPMN, "incoming")).text = fid
        for fid in outgoing[nid]:
            etree.SubElement(el, _q(BPMN, "outgoing")).text = fid
        for ref in node.get("writes", []):
            doa = etree.SubElement(el, _q(BPMN, "dataOutputAssociation"))
            etree.SubElement(doa, _q(BPMN, "targetRef")).text = ref
        marker = node.get("marker")
        if marker == "loop":
            etree.SubElement(el, _q(BPMN, "standardLoopCharacteristics"))
        elif marker in ("miParallel", "miSequential"):
            mi = etree.SubElement(el, _q(BPMN, "multiInstanceLoopCharacteristics"))
            mi.set("isSequential", "true" if marker == "miSequential" else "false")
        if node.get("event") in EVENT_DEF_TAG:
            etree.SubElement(el, _q(BPMN, EVENT_DEF_TAG[node["event"]]))
    for e in edges:
        sf = etree.SubElement(proc, _q(BPMN, "sequenceFlow"))
        sf.set("id", e["_id"]); sf.set("sourceRef", e["source"]); sf.set("targetRef", e["target"])
        if e.get("name"):
            sf.set("name", e["name"])
        if e.get("condition"):
            ce = etree.SubElement(sf, _q(BPMN, "conditionExpression"))
            ce.set(_q(XSI, "type"), "bpmn:tFormalExpression"); ce.text = e["condition"]


def build_collaboration(ir: dict) -> str:
    """Build a 2+-participant collaboration with pools, lanes, and message flows."""
    defs = etree.Element(_q(BPMN, "definitions"), nsmap=NSMAP)
    defs.set("id", "Definitions_1")
    defs.set("targetNamespace", "http://bpmn.intelligence.assistant/generated")
    collab = etree.SubElement(defs, _q(BPMN, "collaboration"))
    collab.set("id", "Collaboration_1")

    parts = ir["participants"]
    all_pos = {}          # node id -> (x, y)
    node_owner = {}       # node id -> participant index
    for pi, p in enumerate(parts):
        part = etree.SubElement(collab, _q(BPMN, "participant"))
        part.set("id", p["id"] + "_pool"); part.set("processRef", p["id"])
        if p.get("name"):
            part.set("name", p["name"])
    for pi, p in enumerate(parts):
        proc = etree.SubElement(defs, _q(BPMN, "process"))
        proc.set("id", p["id"]); proc.set("isExecutable", "false")
        nodes = {n["id"]: n for n in p["nodes"]}
        # optional lanes
        if p.get("lanes"):
            ls = etree.SubElement(proc, _q(BPMN, "laneSet")); ls.set("id", p["id"] + "_ls")
            for li, lane in enumerate(p["lanes"]):
                ln = etree.SubElement(ls, _q(BPMN, "lane"))
                ln.set("id", f"{p['id']}_lane{li}"); ln.set("name", lane.get("name", f"Lane {li}"))
                for ref in lane.get("nodes", []):
                    etree.SubElement(ln, _q(BPMN, "flowNodeRef")).text = ref
        _emit_flow(proc, nodes, p.get("edges", []))
        # layout: each pool is a horizontal band
        band_y = 80 + pi * 220
        for ci, nid in enumerate(nodes):
            all_pos[nid] = (160 + ci * 150, band_y + 60)
            node_owner[nid] = pi

    for i, mf in enumerate(ir.get("messageFlows", []), 1):
        el = etree.SubElement(collab, _q(BPMN, "messageFlow"))
        el.set("id", f"MessageFlow_{i}"); el.set("sourceRef", mf["source"]); el.set("targetRef", mf["target"])
        if mf.get("name"):
            el.set("name", mf["name"])
        mf["_id"] = f"MessageFlow_{i}"

    # ---- DI ----
    diagram = etree.SubElement(defs, _q(BPMNDI, "BPMNDiagram")); diagram.set("id", "BPMNDiagram_1")
    plane = etree.SubElement(diagram, _q(BPMNDI, "BPMNPlane"))
    plane.set("id", "BPMNPlane_1"); plane.set("bpmnElement", "Collaboration_1")
    centre = {}
    # pool shapes
    for pi, p in enumerate(parts):
        n_nodes = len(p["nodes"])
        shp = etree.SubElement(plane, _q(BPMNDI, "BPMNShape"))
        shp.set("id", p["id"] + "_pool_di"); shp.set("bpmnElement", p["id"] + "_pool")
        shp.set("isHorizontal", "true")
        b = etree.SubElement(shp, _q(DC, "Bounds"))
        b.set("x", "120"); b.set("y", str(60 + pi * 220))
        b.set("width", str(max(400, 160 + n_nodes * 150))); b.set("height", "180")
    # node shapes
    for pi, p in enumerate(parts):
        for nid in [n["id"] for n in p["nodes"]]:
            node = next(n for n in p["nodes"] if n["id"] == nid)
            w, h = _shape_size(node["type"])
            x, y = all_pos[nid]
            shp = etree.SubElement(plane, _q(BPMNDI, "BPMNShape"))
            shp.set("id", nid + "_di"); shp.set("bpmnElement", nid)
            bb = etree.SubElement(shp, _q(DC, "Bounds"))
            bb.set("x", str(x)); bb.set("y", str(y)); bb.set("width", str(w)); bb.set("height", str(h))
            centre[nid] = (x + w / 2, y + h / 2)
    # sequence + message edges
    for p in parts:
        for e in p.get("edges", []):
            ed = etree.SubElement(plane, _q(BPMNDI, "BPMNEdge"))
            ed.set("id", e["_id"] + "_di"); ed.set("bpmnElement", e["_id"])
            for pt in (centre[e["source"]], centre[e["target"]]):
                wp = etree.SubElement(ed, _q(DI, "waypoint")); wp.set("x", str(int(pt[0]))); wp.set("y", str(int(pt[1])))
    for mf in ir.get("messageFlows", []):
        ed = etree.SubElement(plane, _q(BPMNDI, "BPMNEdge"))
        ed.set("id", mf["_id"] + "_di"); ed.set("bpmnElement", mf["_id"])
        for pt in (centre[mf["source"]], centre[mf["target"]]):
            wp = etree.SubElement(ed, _q(DI, "waypoint")); wp.set("x", str(int(pt[0]))); wp.set("y", str(int(pt[1])))

    body = etree.tostring(defs, pretty_print=True, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


def build_bpmn(ir: dict) -> str:
    """Build a valid BPMN 2.0 XML string (with DI) from an IR dict.

    Dispatches to the collaboration builder when the IR declares participants.
    """
    if ir.get("participants"):
        return build_collaboration(ir)
    nodes = _validate_ir(ir)
    edges = ir.get("edges", [])
    proc_id = ir.get("process_id", "Process_1")

    # incoming/outgoing flow ids per node
    incoming = {nid: [] for nid in nodes}
    outgoing = {nid: [] for nid in nodes}
    flow_ids = []
    for i, e in enumerate(edges, start=1):
        fid = e.get("id", f"Flow_{i}")
        e["_id"] = fid
        flow_ids.append(fid)
        outgoing[e["source"]].append(fid)
        incoming[e["target"]].append(fid)

    defs = etree.Element(_q(BPMN, "definitions"), nsmap=NSMAP)
    defs.set("id", "Definitions_1")
    defs.set("targetNamespace", "http://bpmn.intelligence.assistant/generated")

    proc = etree.SubElement(defs, _q(BPMN, "process"))
    proc.set("id", proc_id)
    proc.set("isExecutable", "false")
    if ir.get("name"):
        proc.set("name", ir["name"])

    # flow nodes
    for nid, node in nodes.items():
        tag = _element_tag(node["type"])
        el = etree.SubElement(proc, _q(BPMN, tag))
        el.set("id", nid)
        if node.get("name"):
            el.set("name", node["name"])
        # boundary event: attach to an activity, mark interrupting, add a trigger definition
        if node["type"] == "boundaryEvent":
            if node.get("attachedTo"):
                el.set("attachedToRef", node["attachedTo"])
            # cancelActivity default true (interrupting); false = non-interrupting
            el.set("cancelActivity", "true" if node.get("cancelActivity", True) else "false")
        for fid in incoming[nid]:
            inc = etree.SubElement(el, _q(BPMN, "incoming"))
            inc.text = fid
        for fid in outgoing[nid]:
            out = etree.SubElement(el, _q(BPMN, "outgoing"))
            out.text = fid
        # data output associations on an activity (activity writes a data object).
        # (dataInputAssociation would require an ioSpecification/dataInput target; kept out
        #  of scope here — a dataOutputAssociation with a targetRef is the valid minimal form.)
        for ref in node.get("writes", []):
            doa = etree.SubElement(el, _q(BPMN, "dataOutputAssociation"))
            etree.SubElement(doa, _q(BPMN, "targetRef")).text = ref
        # multi-instance / loop marker on an activity
        marker = node.get("marker")
        if marker == "loop":
            etree.SubElement(el, _q(BPMN, "standardLoopCharacteristics"))
        elif marker in ("miParallel", "miSequential"):
            mi = etree.SubElement(el, _q(BPMN, "multiInstanceLoopCharacteristics"))
            mi.set("isSequential", "true" if marker == "miSequential" else "false")
        # typed event trigger (for start/intermediate/end/boundary events)
        ev = node.get("event")
        if ev in EVENT_DEF_TAG:
            etree.SubElement(el, _q(BPMN, EVENT_DEF_TAG[ev]))

    # data objects (referenced by data associations above)
    for d in ir.get("data", []):
        do = etree.SubElement(proc, _q(BPMN, "dataObject"))
        do.set("id", d["id"] + "_do")
        ref = etree.SubElement(proc, _q(BPMN, "dataObjectReference"))
        ref.set("id", d["id"])
        ref.set("dataObjectRef", d["id"] + "_do")
        if d.get("name"):
            ref.set("name", d["name"])
    # data stores: the <dataStore> is a root element; a <dataStoreReference> sits in the process
    for d in ir.get("datastores", []):
        ds = etree.SubElement(defs, _q(BPMN, "dataStore"))
        ds.set("id", d["id"] + "_ds")
        if d.get("name"):
            ds.set("name", d["name"])
        dref = etree.SubElement(proc, _q(BPMN, "dataStoreReference"))
        dref.set("id", d["id"]); dref.set("dataStoreRef", d["id"] + "_ds")
        if d.get("name"):
            dref.set("name", d["name"])

    # sequence flows
    for e in edges:
        sf = etree.SubElement(proc, _q(BPMN, "sequenceFlow"))
        sf.set("id", e["_id"])
        sf.set("sourceRef", e["source"])
        sf.set("targetRef", e["target"])
        if e.get("name"):
            sf.set("name", e["name"])
        if e.get("condition"):
            ce = etree.SubElement(sf, _q(BPMN, "conditionExpression"))
            ce.set(_q(XSI, "type"), "bpmn:tFormalExpression")
            ce.text = e["condition"]

    # artifacts: text annotations (+ association) and groups (after flow elements per XSD order)
    for i, a in enumerate(ir.get("annotations", []), 1):
        ann_id = a.get("id", f"Annotation_{i}")
        ta = etree.SubElement(proc, _q(BPMN, "textAnnotation"))
        ta.set("id", ann_id)
        etree.SubElement(ta, _q(BPMN, "text")).text = a.get("text", "")
        if a.get("attachedTo"):
            assoc = etree.SubElement(proc, _q(BPMN, "association"))
            assoc.set("id", f"{ann_id}_assoc")
            assoc.set("sourceRef", a["attachedTo"]); assoc.set("targetRef", ann_id)
    for i, g in enumerate(ir.get("groups", []), 1):
        gr = etree.SubElement(proc, _q(BPMN, "group"))
        gr.set("id", g.get("id", f"Group_{i}"))

    # ---- DI ----
    pos = _layout(nodes, edges)
    diagram = etree.SubElement(defs, _q(BPMNDI, "BPMNDiagram"))
    diagram.set("id", "BPMNDiagram_1")
    plane = etree.SubElement(diagram, _q(BPMNDI, "BPMNPlane"))
    plane.set("id", "BPMNPlane_1")
    plane.set("bpmnElement", proc_id)
    centre = {}
    for nid, node in nodes.items():
        w, h = _shape_size(node["type"])
        x, y = pos[nid]
        shape = etree.SubElement(plane, _q(BPMNDI, "BPMNShape"))
        shape.set("id", f"{nid}_di")
        shape.set("bpmnElement", nid)
        b = etree.SubElement(shape, _q(DC, "Bounds"))
        b.set("x", str(x)); b.set("y", str(y))
        b.set("width", str(w)); b.set("height", str(h))
        centre[nid] = (x + w / 2, y + h / 2)
    for e in edges:
        edge = etree.SubElement(plane, _q(BPMNDI, "BPMNEdge"))
        edge.set("id", f"{e['_id']}_di")
        edge.set("bpmnElement", e["_id"])
        (sx, sy), (tx, ty) = centre[e["source"]], centre[e["target"]]
        for (wx, wy) in ((sx, sy), (tx, ty)):
            wp = etree.SubElement(edge, _q(DI, "waypoint"))
            wp.set("x", str(int(wx))); wp.set("y", str(int(wy)))

    body = etree.tostring(defs, pretty_print=True, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


if __name__ == "__main__":
    demo = {
        "process_id": "Process_demo", "name": "Demo",
        "nodes": [
            {"id": "start", "type": "startEvent", "name": "Start"},
            {"id": "t1", "type": "userTask", "name": "Do work"},
            {"id": "end", "type": "endEvent", "name": "End"},
        ],
        "edges": [{"source": "start", "target": "t1"}, {"source": "t1", "target": "end"}],
    }
    print(build_bpmn(demo))
