#!/usr/bin/env python3
"""
Shared BPMN validation helpers (TDD §4.3 validation loop).

Two levels, both used by the C2 build pipeline and by validate_rows.py:
  - wellformed(xml)    : XML syntax check (stdlib-free, lxml).
  - schema_valid(xml)  : BPMN 2.0 XSD schema validation via SpiffWorkflow's
                         BpmnValidator. Returns (None, reason) if SpiffWorkflow
                         is not installed, so callers can degrade gracefully.
"""
from __future__ import annotations

from lxml import etree

try:
    from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser, BpmnValidator
    _SPIFF = True
except Exception:  # pragma: no cover
    _SPIFF = False


def spiff_available() -> bool:
    return _SPIFF


def _to_bytes(xml) -> bytes:
    return xml.encode("utf-8") if isinstance(xml, str) else xml


def wellformed(xml):
    """(ok: bool, error: str|None) — is the string well-formed XML?"""
    try:
        etree.fromstring(_to_bytes(xml))
        return True, None
    except etree.XMLSyntaxError as e:
        return False, str(e)


def schema_valid(xml):
    """(ok: bool|None, error: str|None) — does it validate against the BPMN 2.0 XSD?

    ok is None when SpiffWorkflow is unavailable (check skipped, not failed).
    """
    if not _SPIFF:
        return None, "SpiffWorkflow not installed"
    try:
        root = etree.fromstring(_to_bytes(xml))
        parser = BpmnParser(validator=BpmnValidator())
        parser.add_bpmn_xml(etree.ElementTree(root), filename="row.bpmn")
        return True, None
    except Exception as e:  # ValidationException, XMLSyntaxError, etc.
        return False, f"{type(e).__name__}: {str(e)[:200]}"
