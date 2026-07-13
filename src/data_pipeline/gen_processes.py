#!/usr/bin/env python3
"""
Parametric, diversity-controlled process generator (scaling lever, D5/D6 scale-up).

Deep research (Self-Instruct + verification-asymmetry + AttrPrompt topic-guidance)
supports scaling training data by GENERATING candidates and keeping only those that
pass an automatic checker. Here the checker is the existing IR→BPMN-XML builder +
SpiffWorkflow XSD gate (build_c2_dataset.py). To avoid the documented "diversity
collapse" pitfall, generation varies along three independent axes:

    domains (25+ business areas) × structural patterns (linear/xor/parallel/loop/…)
    × natural-language phrasing templates

Each combination yields a distinct NL description + IR seed. Emitted seeds are fed
through build_c2_dataset.py, so any structurally invalid combination is dropped.

Output: a C2 seed file (instruction + ir) — NOT final rows. Marked source
"synthetic-generated" so downstream data carries provenance (needs human review per
Training-Data-Build-Spec Principle 4).

Usage:
    python gen_processes.py --out data/raw/c2_seeds_generated.jsonl [--per-domain 5]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Each domain: a short process vocabulary. steps are (label, taskType); `decide` is a
# yes/no-style decision with two labelled outcome tasks; `loop_step` is a rework task.
DOMAINS = [
    {"id": "leave", "name": "Leave request", "start": "Leave requested", "end": "Request closed",
     "steps": [("Submit leave request", "userTask"), ("Check leave balance", "serviceTask"),
               ("Review request", "userTask")],
     "decide": ("Sufficient balance?", [("approve", "Approve leave", "balance_ok == true"),
                                          ("reject", "Reject leave", "balance_ok == false")]),
     "loop_step": "Amend leave request", "review_step": "Review request"},
    {"id": "procurement", "name": "Procurement", "start": "Purchase need identified", "end": "Order completed",
     "steps": [("Create requisition", "userTask"), ("Select supplier", "userTask"),
               ("Raise purchase order", "serviceTask")],
     "decide": ("Over budget threshold?", [("needs approval", "Obtain manager approval", "amount > 5000"),
                                            ("auto", "Auto-approve order", "amount <= 5000")]),
     "loop_step": "Revise requisition", "review_step": "Review requisition"},
    {"id": "helpdesk", "name": "IT helpdesk", "start": "Ticket raised", "end": "Ticket resolved",
     "steps": [("Categorise ticket", "serviceTask"), ("Diagnose issue", "userTask"),
               ("Apply fix", "userTask")],
     "decide": ("Resolved on first line?", [("resolved", "Confirm resolution", "resolved == true"),
                                             ("escalate", "Escalate to second line", "resolved == false")]),
     "loop_step": "Gather more information", "review_step": "Verify diagnosis"},
    {"id": "onboarding", "name": "Employee onboarding", "start": "New hire accepted", "end": "Onboarding complete",
     "steps": [("Create accounts", "serviceTask"), ("Assign equipment", "userTask"),
               ("Schedule induction", "userTask")],
     "decide": ("Remote employee?", [("remote", "Ship equipment", "remote == true"),
                                      ("onsite", "Prepare desk", "remote == false")]),
     "loop_step": "Correct onboarding details", "review_step": "Review onboarding checklist"},
    {"id": "claims", "name": "Insurance claim", "start": "Claim received", "end": "Claim closed",
     "steps": [("Register claim", "serviceTask"), ("Assess claim", "businessRuleTask"),
               ("Calculate settlement", "serviceTask")],
     "decide": ("Claim valid?", [("pay", "Pay settlement", "valid == true"),
                                 ("decline", "Send decline letter", "valid == false")]),
     "loop_step": "Request missing documents", "review_step": "Review claim details"},
    {"id": "loan", "name": "Loan origination", "start": "Application submitted", "end": "Application closed",
     "steps": [("Capture application", "userTask"), ("Run credit check", "serviceTask"),
               ("Assess affordability", "businessRuleTask")],
     "decide": ("Credit approved?", [("approve", "Disburse funds", "approved == true"),
                                     ("decline", "Notify decline", "approved == false")]),
     "loop_step": "Request further information", "review_step": "Review application"},
    {"id": "returns", "name": "Product return", "start": "Return requested", "end": "Return finalised",
     "steps": [("Validate return request", "serviceTask"), ("Inspect returned item", "userTask"),
               ("Process refund", "serviceTask")],
     "decide": ("Item eligible?", [("refund", "Issue refund", "eligible == true"),
                                   ("reject", "Reject return", "eligible == false")]),
     "loop_step": "Request proof of purchase", "review_step": "Review return request"},
    {"id": "content", "name": "Content publishing", "start": "Draft submitted", "end": "Content published",
     "steps": [("Copy-edit draft", "userTask"), ("Fact-check draft", "userTask"),
               ("Format for publication", "serviceTask")],
     "decide": ("Approved by editor?", [("publish", "Publish content", "approved == true"),
                                        ("revise", "Return for revision", "approved == false")]),
     "loop_step": "Revise draft", "review_step": "Editorial review"},
    {"id": "invoice", "name": "Invoice processing", "start": "Invoice received", "end": "Invoice archived",
     "steps": [("Scan invoice", "serviceTask"), ("Match to purchase order", "serviceTask"),
               ("Post to ledger", "serviceTask")],
     "decide": ("Matches purchase order?", [("pay", "Schedule payment", "matched == true"),
                                            ("query", "Raise query with supplier", "matched == false")]),
     "loop_step": "Correct invoice data", "review_step": "Review invoice"},
    {"id": "recruitment", "name": "Recruitment", "start": "Vacancy opened", "end": "Vacancy closed",
     "steps": [("Screen applications", "userTask"), ("Conduct interview", "userTask"),
               ("Check references", "serviceTask")],
     "decide": ("Candidate suitable?", [("offer", "Make offer", "suitable == true"),
                                        ("reject", "Send rejection", "suitable == false")]),
     "loop_step": "Request additional interview", "review_step": "Review shortlist"},
    {"id": "incident", "name": "Incident management", "start": "Incident detected", "end": "Incident closed",
     "steps": [("Log incident", "serviceTask"), ("Triage severity", "userTask"),
               ("Resolve incident", "userTask")],
     "decide": ("Critical severity?", [("escalate", "Escalate to on-call", "severity == 'critical'"),
                                       ("queue", "Add to standard queue", "severity != 'critical'")]),
     "loop_step": "Collect diagnostics", "review_step": "Review incident record"},
    {"id": "membership", "name": "Membership application", "start": "Application started", "end": "Application complete",
     "steps": [("Complete application form", "userTask"), ("Verify eligibility", "businessRuleTask"),
               ("Set up membership", "serviceTask")],
     "decide": ("Eligible?", [("accept", "Activate membership", "eligible == true"),
                              ("decline", "Notify ineligible", "eligible == false")]),
     "loop_step": "Correct application form", "review_step": "Review application"},
    {"id": "grant", "name": "Grant application", "start": "Proposal received", "end": "Decision issued",
     "steps": [("Check completeness", "serviceTask"), ("Evaluate proposal", "userTask"),
               ("Score proposal", "businessRuleTask")],
     "decide": ("Score above threshold?", [("fund", "Award grant", "score >= 70"),
                                           ("reject", "Decline proposal", "score < 70")]),
     "loop_step": "Request clarifications", "review_step": "Review proposal"},
    {"id": "shipping", "name": "Order shipping", "start": "Order confirmed", "end": "Order delivered",
     "steps": [("Pick items", "userTask"), ("Pack order", "userTask"), ("Dispatch shipment", "serviceTask")],
     "decide": ("In stock?", [("ship", "Ship order", "in_stock == true"),
                              ("backorder", "Create backorder", "in_stock == false")]),
     "loop_step": "Re-check availability", "review_step": "Review order"},
    {"id": "compliance", "name": "Compliance review", "start": "Review triggered", "end": "Review closed",
     "steps": [("Collect evidence", "userTask"), ("Assess controls", "userTask"),
               ("Record findings", "serviceTask")],
     "decide": ("Controls adequate?", [("pass", "Close as compliant", "adequate == true"),
                                       ("remediate", "Raise remediation action", "adequate == false")]),
     "loop_step": "Request additional evidence", "review_step": "Review evidence"},
    {"id": "billing", "name": "Subscription billing", "start": "Billing cycle started", "end": "Cycle closed",
     "steps": [("Calculate charges", "serviceTask"), ("Generate invoice", "serviceTask"),
               ("Collect payment", "serviceTask")],
     "decide": ("Payment successful?", [("receipt", "Send receipt", "paid == true"),
                                        ("retry", "Retry payment", "paid == false")]),
     "loop_step": "Update payment method", "review_step": "Review billing account"},
    {"id": "warranty", "name": "Warranty claim", "start": "Claim lodged", "end": "Claim resolved",
     "steps": [("Verify coverage", "businessRuleTask"), ("Inspect product", "userTask"),
               ("Authorise repair", "userTask")],
     "decide": ("Under warranty?", [("repair", "Repair product", "covered == true"),
                                    ("chargeable", "Quote chargeable repair", "covered == false")]),
     "loop_step": "Request purchase evidence", "review_step": "Review warranty claim"},
    {"id": "access", "name": "Access provisioning", "start": "Access requested", "end": "Access closed",
     "steps": [("Validate request", "serviceTask"), ("Check entitlements", "businessRuleTask"),
               ("Provision access", "serviceTask")],
     "decide": ("Approval required?", [("approve", "Obtain owner approval", "sensitive == true"),
                                       ("grant", "Grant standard access", "sensitive == false")]),
     "loop_step": "Clarify access need", "review_step": "Review access request"},
    {"id": "booking", "name": "Appointment booking", "start": "Booking requested", "end": "Booking confirmed",
     "steps": [("Check availability", "serviceTask"), ("Reserve slot", "serviceTask"),
               ("Send confirmation", "sendTask")],
     "decide": ("Slot available?", [("confirm", "Confirm appointment", "available == true"),
                                    ("waitlist", "Add to waitlist", "available == false")]),
     "loop_step": "Offer alternative slot", "review_step": "Review booking request"},
    {"id": "expense", "name": "Expense reimbursement", "start": "Expense submitted", "end": "Expense closed",
     "steps": [("Check receipts", "userTask"), ("Validate policy", "businessRuleTask"),
               ("Reimburse employee", "serviceTask")],
     "decide": ("Within policy?", [("pay", "Reimburse expense", "within_policy == true"),
                                   ("reject", "Reject expense", "within_policy == false")]),
     "loop_step": "Request missing receipts", "review_step": "Review expense claim"},
    {"id": "quality", "name": "Quality inspection", "start": "Batch produced", "end": "Batch released",
     "steps": [("Sample batch", "userTask"), ("Run tests", "serviceTask"), ("Record results", "serviceTask")],
     "decide": ("Passes QC?", [("release", "Release batch", "passed == true"),
                               ("quarantine", "Quarantine batch", "passed == false")]),
     "loop_step": "Re-test sample", "review_step": "Review test results"},
    {"id": "complaint", "name": "Customer complaint", "start": "Complaint received", "end": "Complaint closed",
     "steps": [("Acknowledge complaint", "sendTask"), ("Investigate complaint", "userTask"),
               ("Propose resolution", "userTask")],
     "decide": ("Customer accepts resolution?", [("close", "Close complaint", "accepted == true"),
                                                  ("escalate", "Escalate complaint", "accepted == false")]),
     "loop_step": "Gather more detail", "review_step": "Review complaint"},
    {"id": "visa", "name": "Visa application", "start": "Application lodged", "end": "Decision sent",
     "steps": [("Check documents", "serviceTask"), ("Conduct background check", "serviceTask"),
               ("Assess application", "userTask")],
     "decide": ("Meets criteria?", [("grant", "Grant visa", "eligible == true"),
                                    ("refuse", "Refuse visa", "eligible == false")]),
     "loop_step": "Request further documents", "review_step": "Review application"},
    {"id": "maintenance", "name": "Equipment maintenance", "start": "Maintenance requested", "end": "Request closed",
     "steps": [("Inspect equipment", "userTask"), ("Order parts", "serviceTask"), ("Perform repair", "userTask")],
     "decide": ("Repairable?", [("repair", "Repair equipment", "repairable == true"),
                                ("replace", "Replace equipment", "repairable == false")]),
     "loop_step": "Re-inspect equipment", "review_step": "Verify repair"},
    {"id": "kyc", "name": "Customer onboarding (KYC)", "start": "Onboarding started", "end": "Onboarding complete",
     "steps": [("Collect identity documents", "userTask"), ("Verify identity", "serviceTask"),
               ("Open account", "serviceTask")],
     "decide": ("Identity verified?", [("open", "Activate account", "verified == true"),
                                       ("review", "Refer to manual review", "verified == false")]),
     "loop_step": "Request clearer documents", "review_step": "Review identity documents"},
    {"id": "payroll", "name": "Payroll run", "start": "Payroll cycle opened", "end": "Payroll completed",
     "steps": [("Import timesheets", "serviceTask"), ("Calculate pay", "serviceTask"),
               ("Approve payroll", "userTask")],
     "decide": ("Totals reconcile?", [("pay", "Release payments", "reconciled == true"),
                                      ("hold", "Hold for correction", "reconciled == false")]),
     "loop_step": "Correct payroll data", "review_step": "Review payroll run"},
    {"id": "refund", "name": "Refund request", "start": "Refund requested", "end": "Refund closed",
     "steps": [("Validate purchase", "serviceTask"), ("Assess refund reason", "userTask"),
               ("Process refund", "serviceTask")],
     "decide": ("Refund approved?", [("refund", "Issue refund", "approved == true"),
                                     ("deny", "Notify denial", "approved == false")]),
     "loop_step": "Request more detail", "review_step": "Review refund request"},
    {"id": "appeal", "name": "Decision appeal", "start": "Appeal lodged", "end": "Appeal closed",
     "steps": [("Register appeal", "serviceTask"), ("Reassess case", "userTask"),
               ("Issue determination", "userTask")],
     "decide": ("Original decision upheld?", [("uphold", "Notify upheld", "upheld == true"),
                                              ("overturn", "Notify overturned", "upheld == false")]),
     "loop_step": "Request supporting evidence", "review_step": "Review appeal"},
    {"id": "hardware", "name": "Hardware provisioning", "start": "Request approved", "end": "Device delivered",
     "steps": [("Reserve device", "serviceTask"), ("Configure device", "userTask"),
               ("Deliver device", "userTask")],
     "decide": ("In stock?", [("provision", "Provision from stock", "in_stock == true"),
                              ("order", "Order new device", "in_stock == false")]),
     "loop_step": "Confirm specification", "review_step": "Review request"},
    {"id": "contract", "name": "Contract approval", "start": "Contract drafted", "end": "Contract executed",
     "steps": [("Legal review", "userTask"), ("Finance review", "userTask"),
               ("Obtain signatures", "userTask")],
     "decide": ("Within delegated authority?", [("sign", "Approve and sign", "within_authority == true"),
                                                ("escalate", "Escalate to board", "within_authority == false")]),
     "loop_step": "Amend contract terms", "review_step": "Review contract"},
]

# NL phrasing templates (varied to reduce diversity collapse).
LINEAR_TEMPLATES = [
    "Generate a BPMN 2.0 diagram for a {name} process: {steps_join}.",
    "Model the following {name} process in BPMN 2.0. First {first}, then {mid}, and finally {last}.",
    "Create a BPMN 2.0 diagram: the {name} process runs {steps_seq}.",
]
XOR_TEMPLATES = [
    "Generate a BPMN 2.0 diagram for a {name} process: {pre}. Then decide — {question} If so, {a}; otherwise {b}.",
    "Model a {name} process in BPMN 2.0 where, after {pre_short}, the process branches on '{question}': one path {a_low}, the other {b_low}.",
]
PARALLEL_TEMPLATES = [
    "Generate a BPMN 2.0 diagram for a {name} process where, after it starts, {p1} and {p2} happen in parallel; once both finish, {last}.",
]
LOOP_TEMPLATES = [
    "Generate a BPMN 2.0 diagram for a {name} process: {pre}, then it is reviewed; if changes are needed the process loops back to {loop}, otherwise it completes with {last}.",
]


def _lower_first(s):
    return s[0].lower() + s[1:] if s else s


def build_linear(d, tmpl_idx):
    steps = d["steps"]
    nodes = [{"id": "start", "type": "startEvent", "name": d["start"]}]
    edges = []
    prev = "start"
    for i, (label, tt) in enumerate(steps, 1):
        nid = f"t{i}"
        nodes.append({"id": nid, "type": tt, "name": label})
        edges.append({"source": prev, "target": nid})
        prev = nid
    nodes.append({"id": "end", "type": "endEvent", "name": d["end"]})
    edges.append({"source": prev, "target": "end"})
    names = [s[0] for s in steps]
    t = LINEAR_TEMPLATES[tmpl_idx % len(LINEAR_TEMPLATES)]
    nl = t.format(name=d["name"].lower(), steps_join="; ".join(_lower_first(n) for n in names),
                  first=_lower_first(names[0]), mid=_lower_first(names[1]), last=_lower_first(names[-1]),
                  steps_seq=" then ".join(_lower_first(n) for n in names))
    return nl, {"process_id": f"Process_{d['id']}_lin", "name": d["name"], "nodes": nodes, "edges": edges}


def build_xor(d, tmpl_idx):
    pre = d["steps"][0]
    q, (aL, aName, aCond), (bL, bName, bCond) = d["decide"][0], d["decide"][1][0], d["decide"][1][1]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "t1", "type": pre[1], "name": pre[0]},
        {"id": "g1", "type": "exclusiveGateway", "name": q},
        {"id": "a", "type": "userTask", "name": aName},
        {"id": "b", "type": "userTask", "name": bName},
        {"id": "g2", "type": "exclusiveGateway", "name": "Merge"},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [
        {"source": "start", "target": "t1"}, {"source": "t1", "target": "g1"},
        {"source": "g1", "target": "a", "name": aL, "condition": aCond},
        {"source": "g1", "target": "b", "name": bL, "condition": bCond},
        {"source": "a", "target": "g2"}, {"source": "b", "target": "g2"},
        {"source": "g2", "target": "end"},
    ]
    t = XOR_TEMPLATES[tmpl_idx % len(XOR_TEMPLATES)]
    nl = t.format(name=d["name"].lower(), pre=_lower_first(pre[0]), pre_short=_lower_first(pre[0]),
                  question=q, a=_lower_first(aName), b=_lower_first(bName),
                  a_low=_lower_first(aName), b_low=_lower_first(bName))
    return nl, {"process_id": f"Process_{d['id']}_xor", "name": d["name"], "nodes": nodes, "edges": edges}


def build_parallel(d, tmpl_idx):
    s = d["steps"]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "split", "type": "parallelGateway", "name": "Fork"},
        {"id": "p1", "type": s[0][1], "name": s[0][0]},
        {"id": "p2", "type": s[1][1], "name": s[1][0]},
        {"id": "join", "type": "parallelGateway", "name": "Join"},
        {"id": "t3", "type": s[2][1], "name": s[2][0]},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [
        {"source": "start", "target": "split"},
        {"source": "split", "target": "p1"}, {"source": "split", "target": "p2"},
        {"source": "p1", "target": "join"}, {"source": "p2", "target": "join"},
        {"source": "join", "target": "t3"}, {"source": "t3", "target": "end"},
    ]
    nl = PARALLEL_TEMPLATES[0].format(name=d["name"].lower(), p1=_lower_first(s[0][0]),
                                      p2=_lower_first(s[1][0]), last=_lower_first(s[2][0]))
    return nl, {"process_id": f"Process_{d['id']}_par", "name": d["name"], "nodes": nodes, "edges": edges}


def build_loop(d, tmpl_idx):
    pre, review, loop = d["steps"][0], d["review_step"], d["loop_step"]
    last = d["steps"][-1]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "t1", "type": pre[1], "name": pre[0]},
        {"id": "rev", "type": "userTask", "name": review},
        {"id": "g1", "type": "exclusiveGateway", "name": "Approved?"},
        {"id": "loop", "type": "userTask", "name": loop},
        {"id": "t2", "type": last[1], "name": last[0]},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [
        {"source": "start", "target": "t1"}, {"source": "t1", "target": "rev"},
        {"source": "rev", "target": "g1"},
        {"source": "g1", "target": "t2", "name": "approved", "condition": "approved == true"},
        {"source": "g1", "target": "loop", "name": "changes needed", "condition": "approved == false"},
        {"source": "loop", "target": "rev"}, {"source": "t2", "target": "end"},
    ]
    nl = LOOP_TEMPLATES[0].format(name=d["name"].lower(), pre=_lower_first(pre[0]),
                                  loop=_lower_first(loop), last=_lower_first(last[0]))
    return nl, {"process_id": f"Process_{d['id']}_loop", "name": d["name"], "nodes": nodes, "edges": edges}


def build_parallel3(d, tmpl_idx):
    """Three activities run concurrently, then join."""
    s = d["steps"]
    nodes = [{"id": "start", "type": "startEvent", "name": d["start"]},
             {"id": "split", "type": "parallelGateway", "name": "Fork"}]
    edges = [{"source": "start", "target": "split"}]
    for i, (label, tt) in enumerate(s[:3], 1):
        nodes.append({"id": f"p{i}", "type": tt, "name": label})
        edges.append({"source": "split", "target": f"p{i}"})
    nodes.append({"id": "join", "type": "parallelGateway", "name": "Join"})
    for i in range(1, min(len(s), 3) + 1):
        edges.append({"source": f"p{i}", "target": "join"})
    nodes.append({"id": "end", "type": "endEvent", "name": d["end"]})
    edges.append({"source": "join", "target": "end"})
    nl = (f"Generate a BPMN 2.0 diagram for a {d['name'].lower()} process where, once it starts, "
          f"{_lower_first(s[0][0])}, {_lower_first(s[1][0])} and {_lower_first(s[2][0])} all run "
          f"concurrently, and the process ends once all three complete.")
    return nl, {"process_id": f"Process_{d['id']}_par3", "name": d["name"], "nodes": nodes, "edges": edges}


def build_xor3(d, tmpl_idx):
    """Three-way exclusive decision (two decision outcomes plus a review/other path)."""
    pre = d["steps"][0]
    q, (aL, aName, aCond), (bL, bName, bCond) = d["decide"][0], d["decide"][1][0], d["decide"][1][1]
    cName = d["review_step"]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "t1", "type": pre[1], "name": pre[0]},
        {"id": "g1", "type": "exclusiveGateway", "name": q},
        {"id": "a", "type": "userTask", "name": aName},
        {"id": "b", "type": "userTask", "name": bName},
        {"id": "c", "type": "userTask", "name": cName},
        {"id": "g2", "type": "exclusiveGateway", "name": "Merge"},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [
        {"source": "start", "target": "t1"}, {"source": "t1", "target": "g1"},
        {"source": "g1", "target": "a", "name": aL, "condition": aCond},
        {"source": "g1", "target": "b", "name": bL, "condition": bCond},
        {"source": "g1", "target": "c", "name": "needs review", "condition": "otherwise"},
        {"source": "a", "target": "g2"}, {"source": "b", "target": "g2"}, {"source": "c", "target": "g2"},
        {"source": "g2", "target": "end"},
    ]
    nl = (f"Generate a BPMN 2.0 diagram for a {d['name'].lower()} process: after {_lower_first(pre[0])}, "
          f"a three-way decision on '{q}' routes the flow to {_lower_first(aName)}, {_lower_first(bName)}, "
          f"or {_lower_first(cName)}, before the process completes.")
    return nl, {"process_id": f"Process_{d['id']}_xor3", "name": d["name"], "nodes": nodes, "edges": edges}


def build_boundary(d, tmpl_idx):
    """A task guarded by an interrupting timer boundary event → escalation handler."""
    s = d["steps"]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "t1", "type": "userTask", "name": s[0][0]},
        {"id": "be", "type": "boundaryEvent", "name": "Time-out", "attachedTo": "t1",
         "event": "timer", "cancelActivity": True},
        {"id": "t2", "type": s[1][1], "name": s[1][0]},
        {"id": "h", "type": "userTask", "name": d["loop_step"]},
        {"id": "end", "type": "endEvent", "name": d["end"]},
        {"id": "end2", "type": "endEvent", "name": "Escalated"},
    ]
    edges = [{"source": "start", "target": "t1"}, {"source": "t1", "target": "t2"},
             {"source": "t2", "target": "end"}, {"source": "be", "target": "h"},
             {"source": "h", "target": "end2"}]
    nl = (f"Generate a BPMN 2.0 diagram for a {d['name'].lower()} process: {_lower_first(s[0][0])}; "
          f"if it is not completed in time, an interrupting timer boundary event escalates by "
          f"{_lower_first(d['loop_step'])}; otherwise the process continues to {_lower_first(s[1][0])}.")
    return nl, {"process_id": f"Process_{d['id']}_bnd", "name": d["name"], "nodes": nodes, "edges": edges}


def build_data(d, tmpl_idx):
    """A linear process where activities read/write data objects."""
    s = d["steps"]
    rec, doc = f"{d['id']}_record", f"{d['id']}_result"
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "t1", "type": s[0][1], "name": s[0][0], "writes": [rec]},
        {"id": "t2", "type": s[1][1], "name": s[1][0], "writes": [doc]},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [{"source": "start", "target": "t1"}, {"source": "t1", "target": "t2"},
             {"source": "t2", "target": "end"}]
    data = [{"id": rec, "name": f"{d['name']} record"}, {"id": doc, "name": f"{d['name']} result"}]
    annotations = [{"id": f"{d['id']}_note", "text": "Retain per data-retention policy", "attachedTo": "t2"}]
    groups = [{"id": f"{d['id']}_grp"}]
    nl = (f"Generate a BPMN 2.0 diagram for a {d['name'].lower()} process that records data: "
          f"{_lower_first(s[0][0])} (producing a {d['name'].lower()} record), then "
          f"{_lower_first(s[1][0])} (producing a result data object), with a text annotation noting "
          f"the retention policy and a group around the recording steps.")
    return nl, {"process_id": f"Process_{d['id']}_data", "name": d["name"], "data": data,
                "annotations": annotations, "groups": groups, "nodes": nodes, "edges": edges}


def build_multiinstance(d, tmpl_idx):
    """A looping/multi-instance activity followed by an aggregation. Rotates the marker
    across parallel MI, sequential MI, and standard loop for full coverage."""
    s = d["steps"]
    marker = ["miParallel", "miSequential", "loop"][tmpl_idx % 3]
    phrase = {"miParallel": "a parallel multi-instance activity (once per item)",
              "miSequential": "a sequential multi-instance activity (one item at a time)",
              "loop": "a looping activity (repeated until complete)"}[marker]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "t1", "type": "userTask", "name": s[1][0], "marker": marker},
        {"id": "t2", "type": "serviceTask", "name": s[2][0]},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [{"source": "start", "target": "t1"}, {"source": "t1", "target": "t2"},
             {"source": "t2", "target": "end"}]
    nl = (f"Generate a BPMN 2.0 diagram for a {d['name'].lower()} process where "
          f"{_lower_first(s[1][0])} is performed as {phrase}, after which "
          f"{_lower_first(s[2][0])} aggregates the results.")
    return nl, {"process_id": f"Process_{d['id']}_mi", "name": d["name"], "nodes": nodes, "edges": edges}


def build_script_complex(d, tmpl_idx):
    """A script task feeding a complex gateway with two branches."""
    s = d["steps"]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "t1", "type": "scriptTask", "name": s[0][0]},
        {"id": "g1", "type": "complexGateway", "name": "Sufficient responses?"},
        {"id": "a", "type": s[1][1], "name": s[1][0]},
        {"id": "b", "type": s[2][1], "name": s[2][0]},
        {"id": "g2", "type": "exclusiveGateway", "name": "Merge"},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [{"source": "start", "target": "t1"}, {"source": "t1", "target": "g1"},
             {"source": "g1", "target": "a"}, {"source": "g1", "target": "b"},
             {"source": "a", "target": "g2"}, {"source": "b", "target": "g2"},
             {"source": "g2", "target": "end"}]
    nl = (f"Generate a BPMN 2.0 diagram for a {d['name'].lower()} process: a script task "
          f"{_lower_first(s[0][0])} feeds a complex gateway that, once enough responses arrive, "
          f"proceeds with {_lower_first(s[1][0])} and {_lower_first(s[2][0])} before completing.")
    return nl, {"process_id": f"Process_{d['id']}_scx", "name": d["name"], "nodes": nodes, "edges": edges}


def build_collab(d, tmpl_idx):
    """A two-pool collaboration with lanes and message flows between participants."""
    s = d["steps"]
    ir = {"name": f"{d['name']} collaboration", "participants": [
        {"id": "Req", "name": "Requester", "nodes": [
            {"id": "r_s", "type": "startEvent", "name": d["start"]},
            {"id": "r_send", "type": "sendTask", "name": "Submit request"},
            {"id": "r_recv", "type": "receiveTask", "name": "Receive outcome"},
            {"id": "r_e", "type": "endEvent", "name": d["end"]}],
         "edges": [{"source": "r_s", "target": "r_send"}, {"source": "r_send", "target": "r_recv"},
                   {"source": "r_recv", "target": "r_e"}]},
        {"id": "Prov", "name": f"{d['name']} team",
         "lanes": [{"name": "Processing", "nodes": ["p_recv", "p_do", "p_send"]}],
         "nodes": [
            {"id": "p_recv", "type": "receiveTask", "name": "Receive request"},
            {"id": "p_do", "type": s[1][1], "name": s[1][0]},
            {"id": "p_send", "type": "sendTask", "name": "Send outcome"},
            {"id": "p_e", "type": "endEvent", "name": "Request handled"}],
         "edges": [{"source": "p_recv", "target": "p_do"}, {"source": "p_do", "target": "p_send"},
                   {"source": "p_send", "target": "p_e"}]}],
        "messageFlows": [{"source": "r_send", "target": "p_recv", "name": "Request"},
                         {"source": "p_send", "target": "r_recv", "name": "Outcome"}]}
    nl = (f"Generate a BPMN 2.0 collaboration diagram for a {d['name'].lower()} process between a "
          f"requester and the {d['name'].lower()} team: the requester submits a request (a message), "
          f"the team receives it, {_lower_first(s[1][0])}, and sends the outcome back to the requester.")
    return nl, ir


def build_misc(d, tmpl_idx):
    """Single process exercising manual task, call activity, and a throwing message event."""
    s = d["steps"]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "t1", "type": "manualTask", "name": s[0][0]},
        {"id": "t2", "type": "callActivity", "name": f"Run {s[1][0].lower()} sub-process"},
        {"id": "thr", "type": "intermediateThrowEvent", "name": "Notify stakeholders", "event": "message"},
        {"id": "t3", "type": "serviceTask", "name": s[2][0]},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [{"source": "start", "target": "t1"}, {"source": "t1", "target": "t2"},
             {"source": "t2", "target": "thr"}, {"source": "thr", "target": "t3"},
             {"source": "t3", "target": "end"}]
    nl = (f"Generate a BPMN 2.0 diagram for a {d['name'].lower()} process: {_lower_first(s[0][0])} "
          f"(a manual task), invoke a reusable sub-process via a call activity, throw a message event "
          f"to notify stakeholders, then {_lower_first(s[2][0])}.")
    return nl, {"process_id": f"Process_{d['id']}_misc", "name": d["name"], "nodes": nodes, "edges": edges}


def build_subprocess_variants(d, tmpl_idx):
    """A process using a transaction and an ad-hoc sub-process."""
    s = d["steps"]
    nodes = [
        {"id": "start", "type": "startEvent", "name": d["start"]},
        {"id": "txn", "type": "transaction", "name": f"{s[0][0]} (transactional)"},
        {"id": "adhoc", "type": "adHocSubProcess", "name": f"{s[1][0]} (ad-hoc)"},
        {"id": "t3", "type": s[2][1], "name": s[2][0]},
        {"id": "end", "type": "endEvent", "name": d["end"]},
    ]
    edges = [{"source": "start", "target": "txn"}, {"source": "txn", "target": "adhoc"},
             {"source": "adhoc", "target": "t3"}, {"source": "t3", "target": "end"}]
    nl = (f"Generate a BPMN 2.0 diagram for a {d['name'].lower()} process: perform "
          f"{_lower_first(s[0][0])} as a transaction sub-process (all-or-nothing), then "
          f"{_lower_first(s[1][0])} as an ad-hoc sub-process (steps in any order), then "
          f"{_lower_first(s[2][0])}.")
    return nl, {"process_id": f"Process_{d['id']}_spv", "name": d["name"], "nodes": nodes, "edges": edges}


PATTERNS = [("linear", build_linear), ("xor", build_xor), ("parallel", build_parallel),
            ("loop", build_loop), ("parallel3", build_parallel3), ("xor3", build_xor3),
            ("boundary", build_boundary), ("data", build_data),
            ("multiinstance", build_multiinstance), ("script_complex", build_script_complex),
            ("collaboration", build_collab), ("misc", build_misc),
            ("subprocess_variants", build_subprocess_variants)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate diverse validated-downstream C2 seeds.")
    ap.add_argument("--out", type=Path, default=Path("data/raw/c2_seeds_generated.jsonl"))
    args = ap.parse_args()

    rows = []
    for di, d in enumerate(DOMAINS):
        for pi, (pname, builder) in enumerate(PATTERNS):
            # vary the NL template per (domain, pattern) so phrasing is not uniform
            nl, ir = builder(d, tmpl_idx=di + pi)
            rows.append({"instruction": nl, "ir": ir,
                         "meta": {"source": "synthetic-generated", "domain": d["id"], "pattern": pname}})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Domains         : {len(DOMAINS)}")
    print(f"Patterns        : {len(PATTERNS)}")
    print(f"Seeds written   : {len(rows)} -> {args.out}")
    print("Feed through build_c2_dataset.py to validate & keep only schema-valid diagrams.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
