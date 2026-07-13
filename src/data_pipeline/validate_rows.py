#!/usr/bin/env python3
"""
D2 — Dataset row validator (the acceptance gate).

Implements the validation half of deliverable D2 in doc/Training-Data-Build-Spec.md
(§7.3, §8). A row must pass this gate before it is accepted into a training set.

Checks (stdlib-only core, always run):
  1. Each line is valid JSON.
  2. Required fields present for the detected row type:
       - SFT / instruction : instruction, output   (input optional)
       - preference / DPO  : prompt, chosen, rejected
  3. No mojibake markers remain (see fix_encoding.py / D1).
  4. No duplicate meta.id values.
  5. Any embedded BPMN XML is well-formed XML (xml.etree).

Deep check (C2 generation rows only, when SpiffWorkflow is installed):
  6. SpiffWorkflow BpmnValidator -> BPMN 2.0 XSD schema validation (see bpmn_validate.py).
     (bpmnlint rule validation is a planned addition; not yet wired.)

Exit code is non-zero if any error-level problem is found, so this can gate CI.

Usage:
    python validate_rows.py <file.jsonl> [--strict]
    --strict   treat warnings (e.g. missing meta) as errors too
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bpmn_validate import schema_valid, spiff_available  # noqa: E402

MOJIBAKE_MARKERS = ("â", "Â", "Ã")
# A field holds an XML *document* only if, after stripping code fences/whitespace,
# it STARTS with one of these. This avoids flagging prose that merely mentions
# "<definitions>" inline (e.g. "The root element is <definitions>.").
XML_DOC_STARTS = ("<?xml", "<definitions", "<bpmn:definitions", "<bpmn:")
FENCE_RE = re.compile(r"```(?:xml)?\s*(.*?)```", re.DOTALL)


def has_mojibake(s: str) -> bool:
    return any(m in s for m in MOJIBAKE_MARKERS)


def extract_xml_documents(text: str) -> list[str]:
    """Extract candidate XML documents from a field.

    1. Any fenced ```xml ... ``` (or plain ``` ... ```) block that looks like XML.
    2. Otherwise, the whole field if it starts with an XML document opener.
    Prose that only mentions a tag inline yields nothing.
    """
    docs = []
    fenced = FENCE_RE.findall(text)
    for block in fenced:
        stripped = block.strip()
        if stripped.startswith(XML_DOC_STARTS):
            docs.append(stripped)
    if not fenced:
        stripped = text.strip()
        if stripped.startswith(XML_DOC_STARTS):
            docs.append(stripped)
    return docs


def find_xml_blocks(row: dict) -> list[tuple[str, str]]:
    """Return (field_name, xml_text) for each extracted XML document in the row."""
    blocks = []
    for field in ("input", "output", "chosen", "rejected"):
        val = row.get(field)
        if isinstance(val, str):
            for doc in extract_xml_documents(val):
                blocks.append((field, doc))
    return blocks


def detect_type(row: dict) -> str:
    if "prompt" in row and "chosen" in row and "rejected" in row:
        return "preference"
    if "instruction" in row and "output" in row:
        return "sft"
    return "unknown"


def validate_xml_wellformed(xml_text: str) -> str | None:
    """Return an error message if the XML is not well-formed, else None."""
    try:
        ET.fromstring(xml_text)
        return None
    except ET.ParseError as e:
        return f"malformed XML: {e}"


def validate_file(path: Path) -> dict:
    """Validate one JSONL dataset. Returns a report dict (no printing, no exit).

    Keys: rows, xml, schema_checked, schema_skipped, errors[], warnings[].
    Shared by main() (CLI) and release_gate.py (D7).
    """
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: dict[str, int] = {}
    n_rows = 0
    n_xml = 0
    n_schema_checked = 0
    n_schema_skipped = 0

    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            n_rows += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"line {lineno}: invalid JSON: {e}")
                continue

            rtype = detect_type(row)
            if rtype == "unknown":
                errors.append(f"line {lineno}: unrecognized row type (missing required fields)")

            # Mojibake
            for k, v in row.items():
                if isinstance(v, str) and has_mojibake(v):
                    errors.append(f"line {lineno}: mojibake in field '{k}' (run fix_encoding.py / D1)")
                    break

            # Duplicate ids
            meta = row.get("meta") or {}
            rid = meta.get("id") if isinstance(meta, dict) else None
            if rid is not None:
                if rid in seen_ids:
                    errors.append(f"line {lineno}: duplicate meta.id '{rid}' (also line {seen_ids[rid]})")
                else:
                    seen_ids[rid] = lineno
            if not isinstance(meta, dict) or "capability" not in meta:
                warnings.append(f"line {lineno}: missing meta.capability (untraceable to a capability)")

            # XML validation policy (Training-Data spec §7.3):
            #  - Generation rows (meta.capability == "C2") MUST emit complete, well-formed XML
            #    that also passes the BPMN 2.0 XSD schema (SpiffWorkflow). Failure -> ERROR.
            #  - All other rows (Q&A/tutoring, critique) embed *illustrative* XML fragments
            #    (opening-tag-only, "..." placeholders) which are pedagogically legitimate
            #    -> malformed = WARNING, not an error.
            cap = meta.get("capability") if isinstance(meta, dict) else None
            for field, xml_text in find_xml_blocks(row):
                n_xml += 1
                err = validate_xml_wellformed(xml_text)
                if err:
                    if cap == "C2":
                        errors.append(f"line {lineno}: field '{field}': {err}")
                    else:
                        warnings.append(f"line {lineno}: field '{field}': illustrative XML fragment, not well-formed as a standalone document (fine for tutoring rows; must be complete for C2)")
                    continue
                if cap == "C2":
                    n_schema_checked += 1
                    ok, why = schema_valid(xml_text)
                    if ok is False:
                        errors.append(f"line {lineno}: field '{field}': fails BPMN 2.0 schema — {why}")
                    elif ok is None:
                        n_schema_skipped += 1

    return {"rows": n_rows, "xml": n_xml, "schema_checked": n_schema_checked,
            "schema_skipped": n_schema_skipped, "errors": errors, "warnings": warnings}


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a BPMN dataset JSONL file (D2).")
    ap.add_argument("file", type=Path)
    ap.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        return 2

    rep = validate_file(args.file)
    n_rows, n_xml = rep["rows"], rep["xml"]
    n_schema_checked, n_schema_skipped = rep["schema_checked"], rep["schema_skipped"]
    errors, warnings = rep["errors"], rep["warnings"]

    # ---- Report ----
    print(f"File            : {args.file}")
    print(f"Rows            : {n_rows}")
    print(f"Rows w/ BPMN XML: {n_xml}")
    print(f"Errors          : {len(errors)}")
    print(f"Warnings        : {len(warnings)}")

    if spiff_available():
        print(f"C2 schema check : SpiffWorkflow active — {n_schema_checked} C2 XML doc(s) validated against the BPMN 2.0 XSD")
    else:
        print(f"C2 schema check : SpiffWorkflow NOT installed — {n_schema_skipped} C2 XML doc(s) not schema-checked (well-formedness only)")
        print("  note: pip install SpiffWorkflow to enable the BPMN 2.0 XSD gate for C2 rows.")

    if errors:
        print("\n--- ERRORS ---")
        for e in errors[:200]:
            print("  " + e)
        if len(errors) > 200:
            print(f"  ... and {len(errors) - 200} more")
    if warnings:
        print("\n--- WARNINGS ---")
        for w in warnings[:50]:
            print("  " + w)
        if len(warnings) > 50:
            print(f"  ... and {len(warnings) - 50} more")

    failed = bool(errors) or (args.strict and bool(warnings))
    print("\nRESULT          :", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
