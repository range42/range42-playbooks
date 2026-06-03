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
