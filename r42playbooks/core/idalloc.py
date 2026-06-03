"""vm_id / IP allocation checks against the global reservation registry.

`scenarios/_reserved.json` is a JSONL file (one JSON object per line) that
records every vm_id/IP claimed across all scenarios. This module validates a
topology's boxes against it and against the project's allocation rules:

  - octet rule: a box's vm_id last 3 digits must equal its IP last octet
    (enforced as an error for newly authored boxes);
  - no duplicate vm_id / IP within the topology;
  - no vm_id / IP collision with a *different* scenario already in the registry
    (re-deploying the topology's own scenario is fine).

Read-only and pure: claiming/writing reservations (with a file lock) is a
separate concern handled by the deploy side, not here.

TOCTOU: ``validate_allocation`` reads the registry at compile time; there is an
inherent race between this check and the deploy-side reservation write. Callers
that compile concurrently must serialize the validate→deploy→record sequence
with an external lock (file lock / DB advisory lock) to avoid two scenarios
claiming the same vm_id/IP.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from r42playbooks.core import constants as C
from r42playbooks.core.errors import TopologyError
from r42playbooks.core.models import Topology


@dataclass(frozen=True)
class ReservedIndex:
    """Parsed view of a JSONL ``_reserved.json`` reservation registry."""

    entries: tuple[dict, ...]

    @classmethod
    def from_file(cls, path: Path) -> "ReservedIndex":
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TopologyError(f"cannot read reservation file: {path}") from exc
        rows: list[dict] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise TopologyError(
                    f"invalid JSON on line {lineno} of {path}"
                ) from exc
        return cls(entries=tuple(rows))

    def used_vm_ids(self) -> set[int]:
        return {int(e["vm_id"]) for e in self.entries if "vm_id" in e}

    def used_ips(self) -> set[str]:
        return {str(e["ip"]) for e in self.entries if "ip" in e}

    def owner_of_vm_id(self, vm_id: int) -> str | None:
        for e in self.entries:
            if int(e.get("vm_id", -1)) == vm_id:
                return e.get("scenario")
        return None

    def owner_of_ip(self, ip: str) -> str | None:
        for e in self.entries:
            if str(e.get("ip", "")) == ip:
                return e.get("scenario")
        return None


@dataclass
class AllocationReport:
    """Result of validate_allocation: human-readable errors + warnings."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_allocation(topology: Topology, reserved: ReservedIndex) -> AllocationReport:
    """Validate a topology's vm_id/IP allocation. Returns a report (never raises)."""
    report = AllocationReport()
    scenario = topology.scenario

    seen_vm_ids: dict[int, str] = {}
    seen_ips: dict[str, str] = {}

    for box in topology.boxes:
        # octet rule (new boxes must comply)
        if not C.octet_matches_vm_id(box.vm_id, box.ip):
            report.errors.append(
                f"box {box.vm_name}: octet rule violated — vm_id {box.vm_id} "
                f"last 3 digits != IP last octet ({box.ip})"
            )

        # intra-topology duplicates
        if box.vm_id in seen_vm_ids:
            report.errors.append(
                f"box {box.vm_name}: duplicate vm_id {box.vm_id} "
                f"(also {seen_vm_ids[box.vm_id]})"
            )
        else:
            seen_vm_ids[box.vm_id] = box.vm_name
        if box.ip in seen_ips:
            report.errors.append(
                f"box {box.vm_name}: duplicate IP {box.ip} (also {seen_ips[box.ip]})"
            )
        else:
            seen_ips[box.ip] = box.vm_name

        # cross-scenario collisions in the registry
        owner = reserved.owner_of_vm_id(box.vm_id)
        if owner is not None and owner != scenario:
            report.errors.append(
                f"box {box.vm_name}: vm_id {box.vm_id} reserved by scenario {owner!r}"
            )
        ip_owner = reserved.owner_of_ip(box.ip)
        if ip_owner is not None and ip_owner != scenario:
            report.errors.append(
                f"box {box.vm_name}: IP {box.ip} reserved by scenario {ip_owner!r}"
            )

    return report
