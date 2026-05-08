"""Range42 topology filter plugins.

Used by scenarios/_universal/main.yml to expand per-team replication
and resolve attachments per inventory hostname.
"""
from __future__ import annotations
import re


def r42_bridge_for_team(bridge_base, team_id):
    """vmbr{bridge_base + team_id}"""
    return f"vmbr{int(bridge_base) + int(team_id)}"


def r42_subnet_for_team(bridge_base, team_id):
    """192.168.{bridge_base + team_id}.0/24"""
    octet = int(bridge_base) + int(team_id)
    return f"192.168.{octet}.0/24"


def r42_vmid_for_node(vmid_base, team_id, seq, vms_per_team):
    """vmid_base + (team_id * vms_per_team) + seq"""
    return int(vmid_base) + (int(team_id) * int(vms_per_team)) + int(seq)


def r42_ip_for_node(bridge_base, team_id, seq):
    """192.168.{bridge_base + team_id}.{200 + seq}; team_id=None -> shared (bridge_base directly)"""
    bb = int(bridge_base)
    octet = bb + (int(team_id) if team_id is not None else 0)
    return f"192.168.{octet}.{200 + int(seq)}"


def r42_expand_per_team(items, team_count):
    """Expand items by replication scope.

    Returns list of {team_id, item} dicts:
    - shared items: team_id=None, sorted by id
    - per_team items: replicated across teams 1..team_count, sorted by id within each team

    Items missing/empty replication or with unknown scope are silently dropped.
    """
    items = items or []
    shared = sorted(
        [i for i in items if (i.get("replication") or {}).get("scope") == "shared"],
        key=lambda i: i.get("id", ""),
    )
    per_team = sorted(
        [i for i in items if (i.get("replication") or {}).get("scope") == "per_team"],
        key=lambda i: i.get("id", ""),
    )
    out = []
    for item in shared:
        out.append({"team_id": None, "item": item})
    for team_id in range(1, int(team_count) + 1):
        for item in per_team:
            out.append({"team_id": team_id, "item": item})
    return out


_HOSTNAME_RE = re.compile(r"^r42\.(?P<prefix>[^-]+)(?:-(?P<team>\d+))?-(?P<name>.+)$")


def r42_attachments_for(topology, inventory_hostname):
    """Return attachments[] for the topology node matching inventory_hostname.

    Hostname pattern: r42.{prefix}-{team}-{name} (per-team) or r42.{prefix}-{name} (shared).
    """
    m = _HOSTNAME_RE.match(inventory_hostname)
    if not m:
        return []
    name = m.group("name")
    for node in topology.get("nodes", []) or []:
        if node.get("id") == name:
            return node.get("attachments", []) or []
    return []


class FilterModule:
    """Ansible filter plugin entry point."""

    def filters(self):
        return {
            "r42_bridge_for_team": r42_bridge_for_team,
            "r42_subnet_for_team": r42_subnet_for_team,
            "r42_vmid_for_node": r42_vmid_for_node,
            "r42_ip_for_node": r42_ip_for_node,
            "r42_expand_per_team": r42_expand_per_team,
            "r42_attachments_for": r42_attachments_for,
        }
