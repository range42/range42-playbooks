"""Deterministic expansion: one play per team.

For every top-level node with ``replication.scope == 'per_team'`` (and each
group's children), emit N copies with per-team offsets applied to vmid, ip,
bridge, vlan, hostname, flag values. Play-level ``notify`` targets and handler
namespaces are rewritten ``<name> -> <name>__team_<id>`` so per-team plays stay
isolated.

Returns an :class:`ExpandResult` with ``plays_per_team`` (== team_count),
``handler_namespaces`` (per-team handler namespace tokens, in emission order),
and the expanded ``document``.

Ported verbatim (behaviour-preserving) from range42-backend-api
``app/overlay/expand_replication.py`` so r42topo stays byte-compatible with the
shared schema/test-vectors and the TypeScript operator. See issue #67.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, TypedDict


class ExpandResult(TypedDict):
    plays_per_team: int
    handler_namespaces: list[str]
    document: dict[str, Any]


_TEMPLATE_RE = re.compile(r"\{(\d*)\s*([+\-*])?\s*team_id\s*\}")


def _render_template(tpl: str, team_id: int) -> str:
    def sub(m: re.Match[str]) -> str:
        base = int(m.group(1) or 0)
        op = m.group(2) or "+"
        if op == "+":
            return str(base + team_id)
        if op == "-":
            return str(base - team_id)
        return str(base * team_id)

    return _TEMPLATE_RE.sub(sub, tpl)


def _apply_offsets(
    node: dict, team_id: int, id_offset: dict | None, namespace_sink: list[str]
) -> dict:
    out = deepcopy(node)
    out["id"] = f"{node['id']}__team_{team_id}"
    cfg = out.get("config") or {}
    if "name_template" in cfg:
        cfg["name"] = _render_template(cfg.pop("name_template"), team_id)
    if "bridge_template" in cfg:
        cfg["bridge"] = _render_template(cfg.pop("bridge_template"), team_id)
    if "vlan_template" in cfg:
        cfg["vlan"] = int(_render_template(cfg.pop("vlan_template"), team_id))
    if "cidr_template" in cfg:
        cfg["cidr"] = _render_template(cfg.pop("cidr_template"), team_id)
    if id_offset and "vmid" in id_offset and "vm_id" in cfg:
        cfg["vm_id"] = int(cfg["vm_id"]) + id_offset["vmid"] * team_id
    out["config"] = cfg
    if isinstance(out.get("networks"), list):
        for nw in out["networks"]:
            if "ip_template" in nw:
                nw["ip"] = _render_template(nw.pop("ip_template"), team_id)
    # Rewrite play-level notify targets + handler namespaces inside attachments.
    for att in out.get("attachments") or []:
        if isinstance(att.get("notify"), list):
            att["notify"] = [f"{n}__team_{team_id}" for n in att["notify"]]
        elif isinstance(att.get("notify"), str):
            att["notify"] = f"{att['notify']}__team_{team_id}"
        if att.get("ansible_primitive") == "handler":
            base_ns = att.get("handler_namespace") or ""
            ns = f"{base_ns}__team_{team_id}" if base_ns else f"team_{team_id}"
            att["handler_namespace"] = ns
            namespace_sink.append(ns)
    return out


def _walk_and_expand(
    nodes: list[dict], team_count: int, namespace_sink: list[str]
) -> list[dict]:
    result: list[dict] = []
    for n in nodes:
        rep = n.get("replication") or {}
        scope = rep.get("scope", "shared")
        if scope == "shared":
            if n.get("kind") == "group" and isinstance(n.get("children"), list):
                nn = deepcopy(n)
                nn["children"] = _walk_and_expand(n["children"], team_count, namespace_sink)
                result.append(nn)
            else:
                result.append(deepcopy(n))
            continue
        # per_team
        id_offset = rep.get("id_offset") or {}
        for tid in range(1, team_count + 1):
            if n.get("kind") == "group" and isinstance(n.get("children"), list):
                expanded_children = [
                    _apply_offsets(c, tid, id_offset, namespace_sink) for c in n["children"]
                ]
                grp = deepcopy(n)
                grp["id"] = f"{n['id']}__team_{tid}"
                grp["children"] = expanded_children
                grp["replication"] = {"scope": "shared"}
                result.append(grp)
            else:
                result.append(_apply_offsets(n, tid, id_offset, namespace_sink))
    return result


def expand_replication(doc: dict, team_count: int) -> ExpandResult:
    """Expand a canonical document into per-team plays. Pure; returns a new doc."""
    if team_count < 1:
        raise ValueError(f"invalid team_count: {team_count}")
    out = deepcopy(doc)
    namespace_sink: list[str] = []
    out["nodes"] = _walk_and_expand(doc.get("nodes", []), team_count, namespace_sink)
    return {
        "plays_per_team": team_count,
        "handler_namespaces": namespace_sink,
        "document": out,
    }
