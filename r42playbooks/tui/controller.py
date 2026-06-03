"""Pure controller behind the Textual TUI — no Textual imports here.

Wraps the api/core so the view stays a thin shell and the logic is unit-testable
(and reusable by the range42 deployment TUI). Holds the in-progress Topology.
"""

from pathlib import Path

from r42playbooks import api
from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.compiler.network_policy import compile_network_policy
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.io import dump_topology
from r42playbooks.core.models import Topology
from r42playbooks.core.scaffold import scaffold_topology


class TuiController:
    """Stateful façade the TUI drives: choose templates, scaffold, validate, save."""

    def __init__(self, catalog_root: Path, reserved_path: Path | None = None) -> None:
        self.catalog = load_catalog(catalog_root)
        self.reserved = (
            ReservedIndex.from_file(reserved_path)
            if reserved_path else ReservedIndex(entries=())
        )
        self.topology: Topology | None = None

    # -- catalog choices --

    def layouts(self) -> list[str]:
        return sorted(self.catalog.subnet_layouts)

    def policies(self) -> list[str]:
        return sorted(self.catalog.network_policies)

    # -- authoring --

    def scaffold(self, *, scenario: str, layout_id: str, policy_id: str) -> Topology:
        self.topology = scaffold_topology(
            self.catalog, scenario=scenario, layout_id=layout_id, policy_id=policy_id
        )
        return self.topology

    def validate(self) -> list[str]:
        if self.topology is None:
            return ["no topology authored yet"]
        return api.validate_topology(self.topology, catalog=self.catalog, reserved=self.reserved)

    def save(self, path: Path) -> Path:
        if self.topology is None:
            raise ValueError("nothing to save — scaffold a topology first")
        return dump_topology(self.topology, Path(path))

    # -- rendering helpers (plain strings; the view decides styling) --

    def summary(self) -> str:
        t = self.topology
        if t is None:
            return "(no topology)"
        lines = [
            f"scenario: {t.scenario}",
            f"subnets:  {', '.join(f'{s.name}={s.cidr}@{s.bridge}' for s in t.subnets)}",
            f"zones:    {', '.join(f'{z.name}({z.role})' for z in t.zones)}",
            f"boxes:    {len(t.boxes)}",
        ]
        lines += [f"  - {b.vm_name} id={b.vm_id} ip={b.ip} zone={b.zone}" for b in t.boxes]
        lines.append(f"policy:   {t.network_policy.template}")
        return "\n".join(lines)

    def rules_text(self) -> str:
        t = self.topology
        if t is None:
            return ""
        pol = self.catalog.resolve_network_policy(t.network_policy.template)
        ver = self.catalog.resolved_version("network_policies", pol.id)
        compiled = compile_network_policy(t, pol, version=ver)
        out = [f"FORWARD rules ({pol.id}@{ver}):"]
        for r in compiled.rules:
            dst = r.destination or r.out_interface or "-"
            port = f":{r.destination_port}" if r.destination_port else ""
            out.append(f"  w{r.weight:<3} {r.jump:<6} {r.source or '-':<18} -> {dst}{port}")
        return "\n".join(out)
