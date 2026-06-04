"""The ``scenario.r42.yml`` composition spec — the "options".

A ``ScenarioSpec`` is the reproducible artifact a user composes: which catalog
modules (subnet layout, network policy, box templates) make up a lab. It is
written verbatim into every generated ``scenarios/<name>/`` so ``new`` is
re-runnable.

Schema-level validation only (shapes, patterns, the security deny-list). Whether
a referenced module *exists* in the catalog is a separate concern (``catalog.py``
``validate_refs``); allocation/rendering happen later still. This layer never
touches the filesystem beyond the load/dump helpers, which reuse ``core.io``'s
atomic writer.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import ValidationError as _PydanticValidationError

import yaml

from r42playbooks.core import constants as C
from r42playbooks.core import io
from r42playbooks.core.errors import TopologyError
from r42playbooks.core.models import Attachment

_STRICT = ConfigDict(extra="forbid")
_no_injection = C.reject_injection


class BoxSpec(BaseModel):
    """One composed box: a catalog box-template pick plus optional tweaks."""

    model_config = _STRICT

    # box_template id (dotless kebab dir under 05_topology_layer/box_templates/).
    template: str = Field(pattern=C.TEMPLATE_ID_RE.pattern)
    # how many VMs this box expands to (vuln-box:count=5 -> vuln-box-00..04).
    count: int = Field(default=1, ge=1, le=C.BOX_COUNT_MAX)
    # extra catalog attachments layered on top of the template's defaults.
    attachments_add: list[Attachment] = Field(default_factory=list)
    # free-form Ansible vars merged into the box (Jinja render surface -> guarded).
    vars: dict[str, Any] = Field(default_factory=dict)
    # §7.1 override: pin the Proxmox template vm_id instead of auto-selecting it.
    template_vm_id: int | None = Field(default=None, ge=C.VM_ID_MIN, le=C.VM_ID_MAX)

    _guard_vars = field_validator("vars")(C.reject_injection_nested)


class ScenarioSpec(BaseModel):
    """The composed lab: catalog picks the renderer turns into a scenario tree."""

    model_config = _STRICT

    schema_version: Literal[1] = 1
    name: str = Field(pattern=C.SCENARIO_NAME_RE.pattern)
    subnet_layout: str = Field(pattern=C.TEMPLATE_ID_RE.pattern)
    # Optional + IGNORED by the generator: isolation is enforced by per-box
    # firewall roles (software.configure.firewalls), not a compiled policy. Kept
    # only so a future scenario-level policy feature can wire it in without a
    # schema change. The parked canonical engine (issue #67) still consumes it.
    network_policy: str | None = Field(default=None, pattern=C.TEMPLATE_ID_RE.pattern)
    boxes: list[BoxSpec] = Field(min_length=1)
    proxmox_node: str | None = Field(default=None, pattern=C.PROXMOX_NODE_RE.pattern)
    notes: str = Field(default="", max_length=255)

    _guard_name = field_validator("name")(_no_injection)
    _guard_notes = field_validator("notes")(_no_injection)


def dumps_spec(spec: ScenarioSpec) -> str:
    """Serialize *spec* to canonical, sorted, newline-terminated YAML."""
    payload = spec.model_dump(mode="json")
    return yaml.safe_dump(
        payload,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )


def dump_spec_atomic(spec: ScenarioSpec, path: Path | str) -> Path:
    """Atomically write *spec* to *path* as canonical YAML. Returns the path."""
    return io.atomic_write_text(dumps_spec(spec), path)


def load_spec(path: Path | str) -> ScenarioSpec:
    """Load and validate a ``scenario.r42.yml`` from *path*.

    :raises TopologyError: if the file is missing, not valid YAML, or fails schema.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TopologyError(f"cannot read scenario spec: {path}") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise TopologyError(f"invalid YAML in scenario spec: {path}") from exc
    if not isinstance(data, dict):
        raise TopologyError(f"scenario spec must be a mapping: {path}")
    try:
        return ScenarioSpec.model_validate(data)
    except _PydanticValidationError as exc:
        raise TopologyError(f"scenario spec schema error in {path}: {exc}") from exc
