#!/usr/bin/env python3
"""
BPMN analyzers for C4 (narrate), C6 (automation opportunities), C7 (compliance).

Deterministic, namespace-agnostic analysis of a BPMN 2.0 diagram, used to generate
correct gold outputs for the C4/C6/C7 datasets (build_analysis_dataset.py) and, at
inference time, as the deterministic tools the model orchestrates (TDD §2, §9). Works
on both the `bpmn:` namespace (our generated diagrams) and the `semantic:` namespace
(MIWG reference models) by matching on element local-names.

Provides:
  parse(xml)                      -> Model
  narrate(model)                  -> str            (C4)
  automation_opportunities(model) -> list[dict]     (C6)
  compliance_check(model, rules)  -> dict           (C7)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from lxml import etree

TASK_TYPES = {"task", "userTask", "serviceTask", "manualTask", "scriptTask",
              "sendTask", "receiveTask", "businessRuleTask", "subProcess", "callActivity",
              "transaction", "adHocSubProcess"}
GATEWAY_TYPES = {"exclusiveGateway", "parallelGateway", "inclusiveGateway",
                 "eventBasedGateway", "complexGateway"}
EVENT_TYPES = {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
               "boundaryEvent"}
# task types that are already system-executed (no human in the loop)
AUTOMATED_TASKS = {"serviceTask", "scriptTask", "businessRuleTask"}
# verbs in a task label that suggest it could be automated
AUTOMATABLE_VERBS = re.compile(
    r"\b(notify|send|email|calculate|compute|validate|verify|check|generate|"
    r"retrieve|fetch|update|record|archive|log|route|assign|classify|"
    r"lookup|look up|transmit|forward|acknowledge|register)\b", re.IGNORECASE)


@dataclass
class Node:
    id: str
    type: str
    name: str = ""


@dataclass
class Edge:
    source: str
    target: str
    name: str = ""
    condition: str = ""


@dataclass
class Model:
    name: str = ""
    nodes: dict = field(default_factory=dict)      # id -> Node
    edges: list = field(default_factory=list)      # Edge
    lanes: dict = field(default_factory=dict)      # lane name -> [element ids]

    def succ(self, nid):
        return [e for e in self.edges if e.source == nid]

    def pred(self, nid):
        return [e for e in self.edges if e.target == nid]

    def by_type(self, *types):
        return [n for n in self.nodes.values() if n.type in types]


def _local(el) -> str:
    return etree.QName(el).localname


def parse(xml) -> Model:
    root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    m = Model()
    # find process element(s)
    procs = [e for e in root.iter() if _local(e) == "process"]
    if procs:
        m.name = procs[0].get("name") or procs[0].get("id") or ""
    for el in root.iter():
        ln = _local(el)
        if ln in TASK_TYPES or ln in GATEWAY_TYPES or ln in EVENT_TYPES:
            m.nodes[el.get("id")] = Node(el.get("id"), ln, el.get("name") or "")
        elif ln == "sequenceFlow":
            cond = ""
            for c in el:
                if _local(c) == "conditionExpression" and c.text:
                    cond = c.text.strip()
            m.edges.append(Edge(el.get("sourceRef"), el.get("targetRef"),
                                el.get("name") or "", cond))
        elif ln == "lane":
            refs = [c.text.strip() for c in el if _local(c) == "flowNodeRef" and c.text]
            m.lanes[el.get("name") or el.get("id")] = refs
    return m


def _topo_order(m: Model):
    indeg = {nid: 0 for nid in m.nodes}
    for e in m.edges:
        if e.target in indeg:
            indeg[e.target] += 1
    from collections import deque
    q = deque([n for n in m.nodes if indeg[n] == 0] or list(m.nodes)[:1])
    order, seen, tmp = [], set(), dict(indeg)
    while q:
        n = q.popleft()
        if n in seen:
            continue
        seen.add(n)
        order.append(n)
        for e in m.succ(n):
            if e.target in tmp:
                tmp[e.target] -= 1
                if tmp[e.target] <= 0:
                    q.append(e.target)
    for n in m.nodes:
        if n not in seen:
            order.append(n)
    return order


def _label(node: Node) -> str:
    return node.name.strip() if node.name else f"an unnamed {node.type}"


_TASK_PHRASE = {
    "userTask": "user task", "serviceTask": "automated service task",
    "manualTask": "manual task", "scriptTask": "script task",
    "sendTask": "send task", "receiveTask": "receive task",
    "businessRuleTask": "business-rule task", "task": "task",
    "subProcess": "sub-process", "callActivity": "call activity",
    "transaction": "transaction sub-process", "adHocSubProcess": "ad-hoc sub-process",
}
_GW_PHRASE = {
    "exclusiveGateway": "exclusive (XOR) gateway", "parallelGateway": "parallel (AND) gateway",
    "inclusiveGateway": "inclusive (OR) gateway", "eventBasedGateway": "event-based gateway",
    "complexGateway": "complex gateway",
}


def narrate(m: Model) -> str:  # C4
    out = []
    starts = m.by_type("startEvent")
    title = f"the process “{m.name}”" if m.name else "the process"
    if starts:
        out.append(f"This narrative describes {title}. It begins with the start event "
                   f"“{_label(starts[0])}”.")
    else:
        out.append(f"This narrative describes {title}.")
    if m.lanes:
        out.append("Responsibilities are divided across the lanes: "
                   + ", ".join(f"“{ln}”" for ln in m.lanes) + ".")
    for nid in _topo_order(m):
        node = m.nodes[nid]
        succ = m.succ(nid)
        if node.type == "startEvent":
            continue
        if node.type == "endEvent":
            out.append(f"The process concludes at the end event “{_label(node)}”.")
        elif node.type in GATEWAY_TYPES:
            if len(succ) > 1:
                branches = []
                for e in succ:
                    tgt = m.nodes.get(e.target)
                    tgt_lbl = _label(tgt) if tgt else e.target
                    cond = e.name or e.condition
                    branches.append(f"to “{tgt_lbl}”" + (f" when {cond}" if cond else ""))
                out.append(f"At the {_GW_PHRASE.get(node.type, 'gateway')} "
                           f"“{_label(node)}” the flow branches " + "; ".join(branches) + ".")
            else:
                tgt = m.nodes.get(succ[0].target) if succ else None
                out.append(f"The {_GW_PHRASE.get(node.type, 'gateway')} “{_label(node)}” "
                           f"merges the incoming paths"
                           + (f" and continues to “{_label(tgt)}”." if tgt else "."))
        elif node.type in TASK_TYPES:
            phrase = _TASK_PHRASE.get(node.type, "task")
            tgt = m.nodes.get(succ[0].target) if len(succ) == 1 else None
            tail = f", after which the flow proceeds to “{_label(tgt)}”." if tgt else "."
            out.append(f"The {phrase} “{_label(node)}” is performed{tail}")
        elif node.type in EVENT_TYPES:
            tgt = m.nodes.get(succ[0].target) if len(succ) == 1 else None
            tail = f", then the flow continues to “{_label(tgt)}”." if tgt else "."
            out.append(f"The intermediate event “{_label(node)}” occurs{tail}")
    return " ".join(out)


def automation_opportunities(m: Model):  # C6
    findings = []
    for node in m.by_type(*TASK_TYPES):
        lbl = _label(node)
        if node.type == "manualTask":
            findings.append({"element_id": node.id, "element": lbl, "current": "manual task",
                             "opportunity": "high",
                             "rationale": f"“{lbl}” is a fully manual task; consider automating it "
                                          f"or replacing it with a system/service task if the work is rule-based."})
        elif node.type == "userTask" and AUTOMATABLE_VERBS.search(lbl):
            findings.append({"element_id": node.id, "element": lbl, "current": "user task",
                             "opportunity": "medium",
                             "rationale": f"The user task “{lbl}” describes an action that is often "
                                          f"automatable (notification, validation, data lookup/update); it "
                                          f"could become a service task."})
    for gw in m.by_type("exclusiveGateway", "inclusiveGateway"):
        if len(m.succ(gw.id)) > 1 and any(e.condition for e in m.succ(gw.id)):
            findings.append({"element_id": gw.id, "element": _label(gw), "current": "manual/data decision",
                             "opportunity": "medium",
                             "rationale": f"The decision at “{_label(gw)}” is condition-based and could "
                                          f"be externalised to a business-rules/DMN service for consistency."})
    return findings


def compliance_check(m: Model, ruleset: dict):  # C7
    results = []
    task_names = " || ".join(_label(n).lower() for n in m.by_type(*TASK_TYPES))
    for rule in ruleset.get("rules", []):
        passed, evidence = False, ""
        rtype = rule["type"]
        if rtype == "require_type":
            hits = m.by_type(rule["param"])
            passed = len(hits) > 0
            evidence = f"found {len(hits)} {rule['param']}" if passed else f"no {rule['param']} present"
        elif rtype == "name_match":
            match = re.search(rule["param"], task_names, re.IGNORECASE)
            passed = match is not None
            evidence = f"matched a step containing '{match.group(0)}'" if match else "no matching step found"
        elif rtype == "has_gateway":
            hits = m.by_type(*GATEWAY_TYPES)
            passed = len(hits) > 0
            evidence = f"{len(hits)} gateway(s) present" if passed else "no decision/branching gateways"
        elif rtype == "cardinality_max":  # 7PMG G3: e.g. exactly/at most one start/end
            n = len(m.by_type(rule["param"]))
            passed = n <= rule.get("max", 1)
            evidence = f"{n} {rule['param']}(s) present (max {rule.get('max', 1)})"
        elif rtype == "size_max":  # 7PMG G1/G7: keep models small
            n = len(m.nodes)
            passed = n <= rule.get("max", 50)
            evidence = f"{n} flow elements (recommended max {rule.get('max', 50)})"
        elif rtype == "forbid_type":  # 7PMG G5: avoid OR routing, etc.
            hits = m.by_type(rule["param"])
            passed = len(hits) == 0
            evidence = "none present" if passed else f"{len(hits)} {rule['param']}(s) present"
        else:
            # Unknown rule type: surface it rather than silently marking the rule failed.
            passed = False
            evidence = f"unsupported rule type '{rtype}' — checker cannot evaluate this rule"
        results.append({"id": rule["id"], "desc": rule["desc"], "severity": rule.get("severity", "low"),
                        "passed": passed, "evidence": evidence})
    n_pass = sum(1 for r in results if r["passed"])
    return {"ruleset": ruleset.get("ruleset", "unnamed"), "passed": n_pass,
            "total": len(results), "results": results}


def compliance_to_text(report: dict) -> str:
    lines = [f"Compliance check against ruleset “{report['ruleset']}”: "
             f"{report['passed']} of {report['total']} rules satisfied."]
    fails = [r for r in report["results"] if not r["passed"]]
    passes = [r for r in report["results"] if r["passed"]]
    if passes:
        lines.append("Satisfied: " + "; ".join(f"{r['desc']} ({r['evidence']})" for r in passes) + ".")
    if fails:
        lines.append("Gaps (recommend addressing):")
        for r in fails:
            lines.append(f"- [{r['severity']}] {r['desc']} — {r['evidence']}.")
    else:
        lines.append("No compliance gaps found against this ruleset.")
    return "\n".join(lines)


def automation_to_text(findings: list) -> str:
    if not findings:
        return ("No clear automation opportunities were identified: the process contains no "
                "manual tasks or obviously automatable user tasks.")
    lines = [f"{len(findings)} automation opportunit{'y' if len(findings) == 1 else 'ies'} identified:"]
    for f in findings:
        lines.append(f"- [{f['opportunity']}] {f['rationale']}")
    return "\n".join(lines)
