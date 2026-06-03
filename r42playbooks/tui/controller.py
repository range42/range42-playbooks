"""Pure controller behind the Textual TUI — no Textual imports here.

Wraps the frozen ``r42playbooks.api`` so the view stays a thin shell and the
compose→generate logic is unit-testable (and reusable by the range42 deployment
TUI). Holds the in-progress composition: a scenario name, a subnet layout, a
network policy, and an ordered list of boxes (template + count).
"""

from pathlib import Path

from pydantic import ValidationError as _PydValidationError

from r42playbooks import api
from r42playbooks.core.allocate import allocate
from r42playbooks.core.errors import TopologyError
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.spec import ScenarioSpec


class ScenarioComposerController:
    """Stateful façade the TUI drives: pick layout/policy, add boxes, generate."""

    def __init__(self, catalog_root: Path, reserved_path: Path | None = None) -> None:
        self.catalog = api.load_catalog(catalog_root)
        self.reserved: ReservedIndex | None = (
            ReservedIndex.from_file(reserved_path) if reserved_path else None
        )
        self.name: str = ""
        self.subnet_layout: str = ""
        self.network_policy: str = ""
        self._boxes: list[tuple[str, int]] = []

    # -- catalog choices --

    def layouts(self) -> list[str]:
        return sorted(self.catalog.subnet_layouts)

    def policies(self) -> list[str]:
        return sorted(self.catalog.network_policies)

    def box_templates(self) -> list[str]:
        return sorted(self.catalog.box_templates)

    def roles(self) -> list[str]:
        return sorted(self.catalog.roles)

    def containers(self) -> list[str]:
        return sorted(self.catalog.containers)

    # -- composition state --

    @property
    def boxes(self) -> list[tuple[str, int]]:
        """The composed (template, count) pairs, in insertion order (a copy)."""
        return list(self._boxes)

    def set_name(self, name: str) -> None:
        self.name = name.strip()

    def set_subnet(self, layout_id: str) -> None:
        self.subnet_layout = layout_id

    def set_policy(self, policy_id: str) -> None:
        self.network_policy = policy_id

    def add_box(self, template: str, count: int = 1) -> None:
        self._boxes.append((template, count))

    def remove_box(self, index: int) -> None:
        self._boxes = [b for i, b in enumerate(self._boxes) if i != index]

    def clear_boxes(self) -> None:
        self._boxes = []

    # -- spec / validation --

    def _missing(self) -> list[str]:
        """Structural gaps that stop a spec from being built (pre-schema)."""
        problems: list[str] = []
        if not self.name:
            problems.append("scenario name is required")
        if not self.subnet_layout:
            problems.append("a subnet layout must be selected")
        if not self.network_policy:
            problems.append("a network policy must be selected")
        if not self._boxes:
            problems.append("add at least one box")
        return problems

    def build_spec(self) -> ScenarioSpec:
        """Assemble the in-progress composition into a ``ScenarioSpec``.

        :raises TopologyError: if the composition is incomplete or schema-invalid.
        """
        missing = self._missing()
        if missing:
            raise TopologyError("; ".join(missing))
        data = {
            "name": self.name,
            "subnet_layout": self.subnet_layout,
            "network_policy": self.network_policy,
            "boxes": [{"template": t, "count": c} for t, c in self._boxes],
        }
        try:
            return ScenarioSpec.model_validate(data)
        except _PydValidationError as exc:
            raise TopologyError(f"invalid composition: {exc}") from exc

    def validate(self) -> list[str]:
        """Return all problems with the current composition ([] == ready)."""
        missing = self._missing()
        if missing:
            return missing
        try:
            spec = self.build_spec()
        except TopologyError as exc:
            return [str(exc)]
        return api.validate_refs(spec, self.catalog)

    # -- preview / generate --

    def preview(self) -> str:
        """A plain-text preview of the composition + its allocated VMs.

        Never raises: validation gaps and allocation errors (e.g. no template
        matches a box spec, subnet exhausted) are returned as text so the TUI
        can show them in-pane instead of crashing.
        """
        problems = self.validate()
        if problems:
            return "not ready:\n" + "\n".join(f"  ✗ {p}" for p in problems)
        try:
            spec = self.build_spec()
            alloc = allocate(spec, self.catalog, self.reserved)
        except TopologyError as exc:
            return f"✗ cannot allocate: {exc}"
        lines = [
            f"scenario: {spec.name}",
            f"subnet layout: {spec.subnet_layout}   policy: {spec.network_policy}",
            f"boxes ({len(alloc.boxes)} VMs):",
        ]
        lines += [
            f"  - {b.vm_name}  id={b.vm_id} ip={b.ip} role={b.role}" for b in alloc.boxes
        ]
        return "\n".join(lines)

    def generate(self, dest: Path, *, overwrite: bool = False) -> Path:
        """Render the composition into ``dest/<name>/`` and return that path.

        :param overwrite: replace an existing ``dest/<name>/`` (default False).
        :raises ScenarioExistsError: target exists and ``overwrite`` is False.
        :raises TopologyError: if the composition is incomplete/invalid or a ref
            cannot be resolved/placed.
        """
        spec = self.build_spec()
        return api.render_scenario(spec, catalog=self.catalog, dest=Path(dest),
                                   reserved=self.reserved, overwrite=overwrite)
