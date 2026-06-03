"""Deterministic compose: base CatalogEntry + ProjectOverlay -> effective doc.

Rules (canonical spec §3):
  - param_overrides: dotted-path mutation of base['defaults'] and nested
    addressing of nodes[].children[].config fields.
  - nodes_added: append to base['nodes'].
  - nodes_removed: drop by id at top level and within group.children.
  - nodes_patched: shallow merge patch into the matching node dict.
  - attachments_added: append to each target_node's attachments list.
  - execution_override: replace base['execution'] if set.

Pure — no I/O, no clocks; identical inputs yield byte-identical effective docs.
Ported behaviour-preserving from range42-backend-api app/overlay/compose.py
(convergence #67) to stay in lock-step with the shared schema/test-vectors.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _apply_param_override(root: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur: Any = root
    for p in parts[:-1]:
        if isinstance(cur, dict):
            cur = cur.setdefault(p, {})
        elif isinstance(cur, list):
            if p.isdigit():
                cur = cur[int(p)]
            else:
                match = next(
                    (x for x in cur if isinstance(x, dict) and x.get("id") == p), None
                )
                if match is None:
                    match = {"id": p}
                    cur.append(match)
                cur = match
        else:
            return
    if isinstance(cur, dict):
        cur[parts[-1]] = value


def _remove_by_id(nodes: list[dict], node_id: str) -> list[dict]:
    out = []
    for n in nodes:
        if n.get("id") == node_id:
            continue
        if isinstance(n.get("children"), list):
            n = dict(n)
            n["children"] = _remove_by_id(n["children"], node_id)
        out.append(n)
    return out


def _patch_by_id(nodes: list[dict], node_id: str, patch: dict) -> None:
    for n in nodes:
        if n.get("id") == node_id:
            n.update(patch)
        if isinstance(n.get("children"), list):
            _patch_by_id(n["children"], node_id, patch)


def _find_node_and_add_attachment(nodes: list[dict], target_id: str, attachment: dict) -> bool:
    for n in nodes:
        if n.get("id") == target_id:
            n.setdefault("attachments", []).append(
                {k: v for k, v in attachment.items() if k != "target_node"}
            )
            return True
        if isinstance(n.get("children"), list):
            if _find_node_and_add_attachment(n["children"], target_id, attachment):
                return True
    return False


def compose(base: dict, overlay: dict | None) -> dict:
    """Apply a ProjectOverlay onto a base CatalogEntry, returning a new effective doc."""
    eff = deepcopy(base)
    if not overlay:
        return eff
    for dotted, value in (overlay.get("param_overrides") or {}).items():
        _apply_param_override(eff, dotted, value)
    for node in overlay.get("nodes_added") or []:
        eff.setdefault("nodes", []).append(deepcopy(node))
    for node_id in overlay.get("nodes_removed") or []:
        eff["nodes"] = _remove_by_id(eff.get("nodes", []), node_id)
    for patch in overlay.get("nodes_patched") or []:
        _patch_by_id(eff.get("nodes", []), patch["id"], deepcopy(patch["patch"]))
    for a in overlay.get("attachments_added") or []:
        tgt = a.get("target_node")
        if tgt:
            _find_node_and_add_attachment(eff.get("nodes", []), tgt, deepcopy(a))
    if overlay.get("execution_override"):
        eff["execution"] = deepcopy(overlay["execution_override"])
    return eff
