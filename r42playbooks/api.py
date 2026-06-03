"""Importable adapter — the surface every frontend calls.

Consumed by the range42-backend-api (FastAPI), r42playbooks's own CLI/TUI, and the
range42 deployment CLI/TUI. Pure: returns plain models / dicts / lists and
raises the ``r42playbooks.core.errors`` hierarchy — never framework types. Each
consumer maps these into its own surface (HTTP envelopes, exit codes, dialogs).
"""

from pydantic import ValidationError as _PydanticValidationError

from r42playbooks.core.catalog import Catalog, load_catalog
from r42playbooks.core.compiler import CompileResult, compile_topology
from r42playbooks.core.errors import ValidationError
from r42playbooks.core.extravars import resolve_universal_extravars
from r42playbooks.core.idalloc import ReservedIndex, validate_allocation
from r42playbooks.core.models import Topology
from r42playbooks.core.validate import semantic_problems

__all__ = [
    "load_catalog",
    "author_topology",
    "validate_topology",
    "compile_topology",
    "resolve_universal_extravars",
    "Catalog",
    "CompileResult",
    "Topology",
    "ReservedIndex",
]


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
