"""Pure VMID allocation.

Ported (behaviour-preserving) from range42-backend-api
``app/core/allocation.py`` @ feature/gamenet-authoring-v1 as part of the
convergence that makes r42topo the single shared topology engine (issue #67).

Only the **pure** ``allocate_vmids`` lives here. The backend's concurrency
mutex (``allocate_vmids_locked``, a module-global ``asyncio.Lock``) and the
SSH ControlMaster helper (``ssh_controlmaster_env``, which mkdir's
``~/.ssh/range42/``) are impure/event-loop-bound and stay in the backend /
future r42runtime — see ``docs/r42topo-port-map.md``.

Allocation scans upward from ``start`` skipping the union of ``reserved`` and
the protected ranges.
"""
from __future__ import annotations

from r42topo.core.vmid_guard import DEFAULT_PROTECTED_RANGES


def _is_protected(v: int, host_overrides: list[list[int]] | None) -> bool:
    for lo, hi in DEFAULT_PROTECTED_RANGES:
        if lo <= v <= hi:
            return True
    if host_overrides:
        # Mirror vmid_guard._effective_ranges' defensiveness (len-guard + int
        # cast) so the two protected-range checks cannot diverge on the same
        # input. The canonical schema constrains overrides to [int, int] pairs.
        for pair in host_overrides:
            if len(pair) == 2 and int(pair[0]) <= v <= int(pair[1]):
                return True
    return False


def allocate_vmids(
    *,
    start: int,
    count: int,
    reserved: set[int],
    host_overrides: list[list[int]] | None,
) -> list[int]:
    out: list[int] = []
    v = start
    while len(out) < count and v < 100000:
        if v not in reserved and not _is_protected(v, host_overrides):
            out.append(v)
        v += 1
    if len(out) < count:
        raise RuntimeError(f"Exhausted VMID range starting at {start}")
    return out
