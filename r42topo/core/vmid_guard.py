"""Protected VMID enforcement.

Ported verbatim (behaviour-preserving) from range42-backend-api
``app/core/vmid_guard.py`` @ feature/gamenet-authoring-v1 as part of the
convergence that makes r42topo the single shared topology engine (issue #67).

Default ranges per range42-deployment/CLAUDE.md. Per-host overrides arrive as
``[[lo, hi], ...]`` pairs (from ``proxmox_hosts.protected_vmids_override``).
``VmidProtectedError`` is a plain ``Exception`` subclass — consumers
(backend-api, CLI, TUI) translate it into their own surface (the backend maps
it to an HTTP 409 envelope); the pure core never imports a web framework.

User memory: never delete VMID 100 (pmg01) / 101 (zbx01) on pve01.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PROTECTED_RANGES: list[tuple[int, int]] = [
    (100, 101),     # pmg01, zbx01
    (1000, 1023),
    (1111, 1111),
    (4000, 4004),
    (9000, 9999),
]


@dataclass
class VmidProtectedError(Exception):
    vmid: int
    reason: str

    @property
    def details(self) -> list[dict[str, str]]:
        return [
            {
                "field": "vm.vm_id",
                "reason": f"{self.vmid} is in protected range ({self.reason})",
            }
        ]


def _effective_ranges(
    host_overrides: list[list[int]] | None,
) -> list[tuple[int, int]]:
    base = list(DEFAULT_PROTECTED_RANGES)
    if host_overrides:
        for pair in host_overrides:
            if len(pair) == 2:
                base.append((int(pair[0]), int(pair[1])))
    return base


def assert_vmid_safe(
    vmid: int, *, host_overrides: list[list[int]] | None
) -> None:
    """Raise ``VmidProtectedError`` if ``vmid`` falls in any effective range."""
    for lo, hi in _effective_ranges(host_overrides):
        if lo <= vmid <= hi:
            raise VmidProtectedError(vmid=vmid, reason=f"{lo}-{hi}")
    return None


def filter_safe_vmids(
    vmids: list[int], *, host_overrides: list[list[int]] | None
) -> tuple[list[int], list[int]]:
    """Partition ``vmids`` into (safe, blocked) for mass-delete preflight."""
    safe: list[int] = []
    blocked: list[int] = []
    for v in vmids:
        try:
            assert_vmid_safe(v, host_overrides=host_overrides)
            safe.append(v)
        except VmidProtectedError:
            blocked.append(v)
    return safe, blocked
