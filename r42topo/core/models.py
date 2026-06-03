"""Pydantic v2 models for topology.json — the authored source of truth.

Schema-level validation only (shapes, patterns, the security deny-list).
Cross-field semantics (zone/subnet referential integrity, IP-in-subnet,
reservation uniqueness) live in the compiler/idalloc layer, not here.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from r42topo.core import constants as C

_STRICT = ConfigDict(extra="forbid")


def _no_injection(value: str) -> str:
    """Reject free-text values containing deny-listed tokens (SSTI/shell/path)."""
    if C.violates_denylist(value):
        raise ValueError("value contains a forbidden character or pattern")
    return value


class Attachment(BaseModel):
    """A catalog item dispatched onto a box (role / container / gamification)."""

    model_config = _STRICT

    kind: Literal["role", "container", "gamification"]
    catalog_ref: str = Field(pattern=C.CATALOG_REF_RE.pattern)
    params: dict[str, Any] = Field(default_factory=dict)


class Subnet(BaseModel):
    """A concrete L3 subnet bound to a Proxmox bridge."""

    model_config = _STRICT

    name: str = Field(pattern=C.VM_NAME_RE.pattern)
    cidr: str = Field(pattern=C.IPV4_CIDR_RE.pattern)
    bridge: str = Field(pattern=C.BRIDGE_RE.pattern)
    gateway: str | None = Field(default=None, pattern=C.IPV4_RE.pattern)

    _guard_name = field_validator("name")(_no_injection)


class Zone(BaseModel):
    """A logical isolation zone mapped onto one subnet."""

    model_config = _STRICT

    name: str = Field(pattern=C.VM_NAME_RE.pattern)
    subnet: str = Field(pattern=C.VM_NAME_RE.pattern)  # FK -> Subnet.name
    role: Literal["admin", "ctf", "team", "student", "template"]

    _guard_name = field_validator("name")(_no_injection)


class Box(BaseModel):
    """A single VM to create and configure."""

    model_config = _STRICT

    vm_name: str = Field(pattern=C.VM_NAME_RE.pattern)
    vm_id: int = Field(ge=C.VM_ID_MIN, le=C.VM_ID_MAX)
    ip: str = Field(pattern=C.IPV4_RE.pattern)
    zone: str = Field(pattern=C.VM_NAME_RE.pattern)  # FK -> Zone.name
    box_template: str = Field(pattern=C.CATALOG_REF_RE.pattern)
    inventory_group: str = Field(pattern=C.INVENTORY_GROUP_RE.pattern)
    attachments: list[Attachment] = Field(default_factory=list)

    _guard_vm_name = field_validator("vm_name")(_no_injection)


class NetworkPolicyRef(BaseModel):
    """Reference to a catalog network-isolation policy template + overrides."""

    model_config = _STRICT

    template: str = Field(pattern=C.CATALOG_REF_RE.pattern)
    overrides: dict[str, Any] = Field(default_factory=dict)


class Topology(BaseModel):
    """Top-level authored topology — the source of truth the compiler expands."""

    model_config = _STRICT

    schema_version: int = 1
    scenario: str = Field(pattern=C.SCENARIO_NAME_RE.pattern)
    description: str = ""
    proxmox_node: str = Field(pattern=C.PROXMOX_NODE_RE.pattern)
    subnets: list[Subnet] = Field(min_length=1)
    zones: list[Zone] = Field(min_length=1)
    boxes: list[Box] = Field(min_length=1)
    network_policy: NetworkPolicyRef
