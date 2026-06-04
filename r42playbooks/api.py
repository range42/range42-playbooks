"""Importable adapter — the surface every frontend calls.

Consumed by the range42-backend-api (FastAPI), r42playbooks's own CLI/TUI, and the
range42 deployment CLI/TUI. Pure: returns plain models / dicts / lists and
raises the ``r42playbooks.core.errors`` hierarchy — never framework types. Each
consumer maps these into its own surface (HTTP envelopes, exit codes, dialogs).
"""

from pathlib import Path

from pydantic import ValidationError as _PydanticValidationError

from r42playbooks.core.allocate import Allocation, allocate
from r42playbooks.core.catalog import (
    Catalog,
    list_containers,
    list_images,
    list_roles,
    load_catalog,
    validate_refs,
)
from r42playbooks.core.compiler import CompileResult, compile_topology
from r42playbooks.core.errors import ScenarioExistsError, ValidationError
from r42playbooks.core.extravars import resolve_universal_extravars
from r42playbooks.core.idalloc import ReservedIndex, validate_allocation
from r42playbooks.core.models import Topology
from r42playbooks.core.render import render_scenario as _render_scenario
from r42playbooks.core.spec import ScenarioSpec, dump_spec_atomic, load_spec
from r42playbooks.core.validate import semantic_problems

__all__ = [
    # generator surface (FROZEN at S5a — consumed by the CLI/TUI/backend)
    "load_catalog",
    "list_images",
    "list_roles",
    "list_containers",
    "validate_refs",
    "load_spec",
    "dump_spec_atomic",
    "allocate",
    "render_scenario",
    "ScenarioSpec",
    "Allocation",
    "Catalog",
    "ReservedIndex",
    "ScenarioExistsError",
    # legacy topology-compiler surface (pre-pivot; kept for compatibility)
    "author_topology",
    "validate_topology",
    "compile_topology",
    "resolve_universal_extravars",
    "CompileResult",
    "Topology",
]


def render_scenario(
    spec: ScenarioSpec,
    *,
    catalog: Catalog,
    dest: Path,
    reserved: ReservedIndex | None = None,
    overwrite: bool = False,
) -> Path:
    """Allocate *spec* against *catalog* and render a ``scenarios/<name>/`` tree.

    The single entry point a frontend calls to go from a composition spec to a
    deployable scenario directory. Returns the scenario root path.

    Note: this resolves box templates but does NOT pre-validate role/container
    attachment names — call :func:`validate_refs` first (the CLI/TUI do) to
    typo-guard ``attachments_add`` / ``default_attachments`` before generating.
    Deny-list guards on every field still apply at schema-validation time.

    :param overwrite: if False (default) and the target dir exists, raise
        :class:`~r42playbooks.core.errors.ScenarioExistsError` instead of clobbering.
    :raises CatalogNotFoundError: a referenced subnet layout / box template is unknown.
    :raises CompileError: a box cannot be placed (no subnet, exhausted ids/octets).
    :raises ScenarioExistsError: target exists and ``overwrite`` is False.
    """
    alloc = allocate(spec, catalog, reserved)
    return _render_scenario(alloc, spec, dest=Path(dest), overwrite=overwrite)


def author_topology(spec: dict, *, catalog: Catalog) -> Topology:
    """Validate a raw author spec into a Topology, rejecting dangling catalog refs.

    :raises ValidationError: on schema failure or a reference the catalog can't resolve.
    """
    try:
        topology = Topology.model_validate(spec)
    except _PydanticValidationError as exc:
        raise ValidationError(f"invalid topology: {exc}") from exc

    problems = semantic_problems(topology, catalog)
    if problems:
        raise ValidationError("topology references unresolved items: " + "; ".join(problems))
    return topology


def validate_topology(
    topology: Topology, *, catalog: Catalog, reserved: ReservedIndex
) -> list[str]:
    """Return all problems (semantic + allocation) with a topology ([] == valid)."""
    problems = list(semantic_problems(topology, catalog))
    problems.extend(validate_allocation(topology, reserved).errors)
    return problems
