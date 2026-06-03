"""Fail-closed deny-list for free-text fields that flow into Ansible variables.

The deny-list rejects (never sanitizes) Jinja/SSTI (`{{ }}`, `{% %}`, `${`),
shell metacharacters, NUL/newlines, path traversal, and argv-flag injection.

Extracted from the retired invented-model `constants.py` during the canonical
convergence (issue #67). It is applied to the **canonical** free-text surface —
``config`` / ``vars`` / ``defaults`` / ``param_overrides`` — by
``r42topo.api`` (see ``assert_document_safe``). It is deliberately NOT applied
to the schema's controlled ``*_template`` fields (``cidr_template``,
``bridge_template``, ``ip_template``, ``value_template``), which legitimately
contain ``{{ bridge_base + team_id }}`` and are rendered by a safe
substitution pass.
"""
from __future__ import annotations

from typing import Any

# Substrings that must never appear in a free-text topology field.
DENYLIST_SUBSTRINGS: tuple[str, ...] = (
    "{{", "}}", "{%", "%}", "${", "`", ";", "|", "&", "\n", "\r", "\x00", "..",
)


def violates_denylist(value: str) -> bool:
    """Return True if *value* contains any denied substring or a leading dash."""
    if value.startswith("-"):
        return True
    return any(token in value for token in DENYLIST_SUBSTRINGS)


def reject_injection(value: str) -> str:
    """Raise ``ValueError`` if *value* is deny-listed; else return it unchanged."""
    if violates_denylist(value):
        raise ValueError("value contains a forbidden character or pattern")
    return value


def nested_violations(obj: Any, *, path: str = "") -> list[str]:
    """Recursively collect dotted paths of every deny-listed string in *obj*.

    Walks dict keys+values and list items. Used for free-form ``config`` /
    ``vars`` / ``defaults`` / ``param_overrides`` whose values flow into Ansible
    variables (a Jinja2 render surface). Returns ``[]`` when *obj* is clean.
    """
    out: list[str] = []
    if isinstance(obj, str):
        if violates_denylist(obj):
            out.append(path or "<value>")
    elif isinstance(obj, dict):
        for key, val in obj.items():
            key_path = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and violates_denylist(key):
                out.append(f"{key_path} (key)")
            out.extend(nested_violations(val, path=key_path))
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            out.extend(nested_violations(item, path=f"{path}[{idx}]"))
    return out


def _scan_nodes(nodes: list[dict], prefix: str) -> list[str]:
    out: list[str] = []
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        npath = f"{prefix}[{node.get('id', idx)}]"
        cfg = node.get("config")
        if isinstance(cfg, dict):
            out.extend(f"{npath}.config.{p}" for p in nested_violations(cfg))
        for j, att in enumerate(node.get("attachments") or []):
            if isinstance(att, dict) and isinstance(att.get("vars"), dict):
                out.extend(
                    f"{npath}.attachments[{j}].vars.{p}"
                    for p in nested_violations(att["vars"])
                )
        children = node.get("children")
        if isinstance(children, list):
            out.extend(_scan_nodes(children, f"{npath}.children"))
    return out


def document_freetext_violations(doc: dict) -> list[str]:
    """Collect deny-list violations in a canonical document's free-text surface.

    Scans exactly the user-supplied fields that flow into Ansible variables —
    top-level ``defaults`` and each node's ``config`` / attachment ``vars``
    (recursing into ``children``). Deliberately does NOT scan the schema's
    controlled ``*_template`` fields (``cidr_template`` / ``bridge_template`` /
    ``ip_template`` / ``value_template``), which legitimately contain
    ``{{ bridge_base + team_id }}``. Returns ``[]`` for a clean document.
    """
    out: list[str] = []
    defaults = doc.get("defaults")
    if isinstance(defaults, dict):
        out.extend(f"defaults.{p}" for p in nested_violations(defaults))
    out.extend(_scan_nodes(doc.get("nodes") or [], "nodes"))
    return out
