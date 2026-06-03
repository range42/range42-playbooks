"""Pydantic models for the catalog templates under 05_topology_layer/.

Three template kinds, all authored as YAML, validated here:
  - BoxTemplate           (box_templates/)    VM/box archetypes
  - NetworkPolicyTemplate (network_policies/) symbolic isolation policies
  - SubnetLayout          (subnet_layouts/)   subnet/bridge layouts

Templates carry *symbolic* structure only (zone names, service ports) — no
concrete per-scenario IPs beyond declared params/defaults. The compiler (P3)
binds symbols to a topology's concrete subnets/IPs.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from r42topo.core import constants as C
from r42topo.core.models import Attachment, Subnet

_STRICT = ConfigDict(extra="forbid")


# --- box templates ---------------------------------------------------------

class BoxTemplate(BaseModel):
    """A VM/box archetype: role, default inventory group, spec, attachments."""

    model_config = _STRICT

    id: str = Field(pattern=C.TEMPLATE_ID_RE.pattern)
    api_version: int = 1
    description: str = ""
    role: Literal["admin", "ctf", "team", "student", "template"]
    default_inventory_group: str = Field(pattern=C.INVENTORY_GROUP_RE.pattern)
    spec: str = Field(min_length=1)
    default_attachments: list[Attachment] = Field(default_factory=list)


# --- subnet layouts --------------------------------------------------------

class SubnetLayout(BaseModel):
    """A reusable set of subnet/bridge declarations a topology can adopt."""

    model_config = _STRICT

    id: str = Field(pattern=C.TEMPLATE_ID_RE.pattern)
    api_version: int = 1
    description: str = ""
    subnets: list[Subnet] = Field(min_length=1)


# --- network policy templates ---------------------------------------------

class PortSpec(BaseModel):
    """A protocol + optional port (range). port is None for icmp/all-ports."""

    model_config = _STRICT

    proto: Literal["tcp", "udp", "icmp"]
    port: int | None = Field(default=None, ge=1, le=65535)
    port_end: int | None = Field(default=None, ge=1, le=65535)


class ZoneDecl(BaseModel):
    """A symbolic zone; `wan: true` marks the uplink/internet pseudo-zone."""

    model_config = _STRICT

    name: str = Field(pattern=C.VM_NAME_RE.pattern)
    wan: bool = False


class ServiceEndpoint(BaseModel):
    """A named service inside a zone, addressable in the matrix as `svc:<name>`."""

    model_config = _STRICT

    name: str = Field(pattern=C.VM_NAME_RE.pattern)
    zone: str = Field(pattern=C.VM_NAME_RE.pattern)
    ports: list[PortSpec] = Field(min_length=1)


class MatrixRule(BaseModel):
    """One intent cell: src zone -> dst (zone | `svc:<name>`) with an action."""

    model_config = _STRICT

    src: str = Field(pattern=C.MATRIX_SRC_RE.pattern)
    dst: str = Field(pattern=C.MATRIX_DST_RE.pattern)
    action: Literal["accept", "drop", "reject"]
    ports: list[PortSpec] = Field(default_factory=list)
    comment: str | None = Field(default=None, max_length=200)

    _guard_comment = field_validator("comment")(
        lambda v: C.reject_injection(v) if v is not None else v
    )


class PolicyDefaults(BaseModel):
    """Catch-all behaviour the compiler synthesizes around explicit matrix rules."""

    model_config = _STRICT

    default_action: Literal["drop", "reject", "accept"] = "drop"
    accept_established_related: bool = True
    allow_intra_zone: bool = True
    airgap_zones: list[str] = Field(default_factory=list)


class NetworkPolicyTemplate(BaseModel):
    """A symbolic, parametric isolation policy (generalizes 05_network_isolation)."""

    model_config = _STRICT

    id: str = Field(pattern=C.TEMPLATE_ID_RE.pattern)
    api_version: int = 1
    kind: Literal["isolation-policy"]
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    zones: list[ZoneDecl] = Field(min_length=1)
    services: list[ServiceEndpoint] = Field(default_factory=list)
    matrix: list[MatrixRule] = Field(default_factory=list)
    defaults: PolicyDefaults = Field(default_factory=PolicyDefaults)
