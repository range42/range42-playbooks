"""Preflight checks — structured, enumerated, framework-free.

Ported (behaviour-preserving) from range42-backend-api
``app/core/preflight.py`` @ feature/gamenet-authoring-v1 as part of the
convergence that makes r42topo the single shared topology engine (issue #67).

Only the **pure, synchronous, no-I/O** subset lives here:
``check_vmids``, ``check_resource_budget``, ``check_secret_completeness``,
``check_topology_node_role`` and ``check_vmid_safety_for_topology``. The
backend's filesystem check (``check_topology_assets``), its ``httpx`` network
checks (``check_proxmox_api_status`` / ``check_sdn_bridge`` /
``check_docker_image_pull`` / ``check_git_reachable``) and the
``run_declarative_checks`` dispatcher are impure and stay in the backend /
future r42runtime — see ``docs/r42topo-port-map.md``. This module therefore
imports neither ``httpx`` nor any web framework.

Each check returns a ``PreflightCheck`` with result ∈ {pass, warn, block}.
The aggregate ``PreflightReport.result`` is ``block`` if any check blocks,
else ``warn`` if any warns, else ``pass``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from r42topo.core.vmid_guard import VmidProtectedError, assert_vmid_safe

Result = Literal["pass", "warn", "block"]


@dataclass
class PreflightCheck:
    check: str
    result: Result
    detail: str = ""
    field_path: str | None = None
    code: str | None = None


@dataclass
class PreflightReport:
    checks: list[PreflightCheck] = field(default_factory=list)

    @property
    def result(self) -> Result:
        if any(c.result == "block" for c in self.checks):
            return "block"
        if any(c.result == "warn" for c in self.checks):
            return "warn"
        return "pass"


def check_vmids(
    requested: list[int], *, host_overrides: list[list[int]] | None
) -> PreflightCheck:
    for v in requested:
        try:
            assert_vmid_safe(v, host_overrides=host_overrides)
        except VmidProtectedError as e:
            return PreflightCheck(
                check="vmid_collision",
                result="block",
                detail=f"VMID {e.vmid} in protected range",
                field_path="vm.vm_id",
            )
    if len(set(requested)) != len(requested):
        return PreflightCheck(
            check="vmid_collision",
            result="block",
            detail="duplicate VMIDs in plan",
            field_path="vm.vm_id",
        )
    return PreflightCheck(check="vmid_collision", result="pass")


def check_resource_budget(
    *, total_ram_mb_required: int, host_total_ram_mb: int
) -> PreflightCheck:
    if host_total_ram_mb <= 0:
        return PreflightCheck(
            check="resource_budget",
            result="block",
            detail="Host capacity unknown",
            field_path="target_host_id",
        )
    ratio = total_ram_mb_required / host_total_ram_mb
    if ratio > 1.10:
        return PreflightCheck(
            check="resource_budget",
            result="block",
            detail=f"{total_ram_mb_required}MB required > {host_total_ram_mb}MB capacity",
            field_path="team_count",
        )
    if ratio > 0.90:
        return PreflightCheck(
            check="resource_budget",
            result="warn",
            detail=f"{int(ratio * 100)}% of host capacity",
            field_path="team_count",
        )
    return PreflightCheck(check="resource_budget", result="pass")


def check_secret_completeness(
    env: list[dict], provided: dict[str, str] | None
) -> PreflightCheck:
    missing = [
        e["name"]
        for e in env
        if e.get("secret") and e.get("required", True) and e["name"] not in (provided or {})
    ]
    if missing:
        return PreflightCheck(
            check="secret_completeness",
            result="block",
            detail=f"Missing required secrets: {','.join(missing)}",
            field_path="secrets",
        )
    return PreflightCheck(check="secret_completeness", result="pass")


def check_vmid_safety_for_topology(
    topology: dict,
    team_count: int,
    host_overrides: list[list[int]] | None,
) -> PreflightCheck:
    """Wrap ``check_vmids()`` with topology-aware VMID expansion.

    Mirrors the universal playbook's ``r42_vmid_for_node`` filter:
    - shared scope: ``(vmid_base or template_vmid) + seq`` (seq within shared list)
    - per_team scope: for ``team_id in 1..team_count``,
      ``(vmid_base or template_vmid) + (team_id * vms_per_team) + seq``
      (seq within per-team list, ``vms_per_team`` = total per-team VM count).

    Pure and synchronous (the backend marked it ``async`` only for call-site
    symmetry with the deferred network checks; it performs no I/O).
    """
    nodes = topology.get("nodes") or []
    vm_kinds = ("vm", "lxc")

    shared_vms = [
        n for n in nodes
        if n.get("kind") in vm_kinds
        and (n.get("replication") or {}).get("scope") == "shared"
    ]
    per_team_vms = [
        n for n in nodes
        if n.get("kind") in vm_kinds
        and (n.get("replication") or {}).get("scope") == "per_team"
    ]

    vmids: list[int] = []

    # Shared VMs use vmid_base + seq
    for seq, n in enumerate(shared_vms):
        base = n.get("vmid_base", n.get("template_vmid", 0))
        vmids.append(int(base) + seq)

    # Per-team: vmid_base + (team_id * vms_per_team) + seq
    vms_per_team = len(per_team_vms)
    for team_id in range(1, team_count + 1):
        for seq, n in enumerate(per_team_vms):
            base = n.get("vmid_base", n.get("template_vmid", 0))
            vmids.append(int(base) + (team_id * vms_per_team) + seq)

    return check_vmids(vmids, host_overrides=host_overrides)


def check_topology_node_role(topology: dict) -> list[PreflightCheck]:
    """Every VM/LXC topology node must declare a non-empty 'role'."""
    checks: list[PreflightCheck] = []
    for node in (topology.get("nodes") or []):
        if node.get("kind") not in ("vm", "lxc"):
            continue
        if not node.get("role"):
            checks.append(PreflightCheck(
                check="topology_node_role",
                result="block",
                detail=f"VM/LXC node {node.get('id')} missing 'role'",
                field_path=f"nodes[{node.get('id')}]",
                code="TOPOLOGY_NODE_MISSING_ROLE",
            ))
    if not checks:
        checks.append(PreflightCheck(
            check="topology_node_role",
            result="pass",
            detail="all VM/LXC nodes have role",
        ))
    return checks
