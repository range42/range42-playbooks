"""Pydantic models for catalog layers.

Loaded artifacts:
  - ImageDef              (01_image_layer/)    base VM image descriptors
  - BoxTemplate           (box_templates/)     VM/box archetypes
  - NetworkPolicyTemplate (network_policies/)  symbolic isolation policies
  - SubnetLayout          (subnet_layouts/)    subnet/bridge layouts

Templates carry *symbolic* structure only (zone names, service ports) — no
concrete per-scenario IPs beyond declared params/defaults. The compiler (P3)
binds symbols to a topology's concrete subnets/IPs.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from r42playbooks.core import constants as C
from r42playbooks.core.models import Attachment, Subnet

_STRICT = ConfigDict(extra="forbid")


# --- base images (01_image_layer) -----------------------------------------

class CloudImageSpec(BaseModel):
    """A cloud image download target: URL to fetch + filename on Proxmox local storage."""

    model_config = _STRICT

    url: str = Field(min_length=1)
    filename: str = Field(min_length=1)


class ProxmoxTemplateSpec(BaseModel):
    """One Proxmox 9xxx template VM entry — the render source for stage_01 create plays.

    Mirrors a row in ``TEMPLATE_TABLE`` but lives in the catalog so the generator
    renders ``stage_01-create_templates/templates/<image>/<vm_name>.yml`` without
    any hardcoded data in the playbooks repo.
    """

    model_config = _STRICT

    vm_id: int
    vm_name: str = Field(min_length=1)
    spec: str = Field(min_length=1)   # "Xcpu/Ygb/Zgb"
    ip: str = Field(pattern=C.IPV4_RE.pattern)
    bridge: str = Field(pattern=C.BRIDGE_RE.pattern, default="vmbr140")


class ImageDef(BaseModel):
    """Base VM image descriptor — the canonical name + distro metadata.

    id matches ``<distro>_<codename>`` (IMAGE_RE), e.g. ``ubuntu_noble``.
    Box templates reference images by id; validate_refs checks that the id
    exists in the catalog's 01_image_layer.
    cloud_image carries the download coordinates used by the generator to
    render stage_00-download_cloudinit_files/<image>.yml.
    proxmox_templates carries the per-VM create coordinates used to render
    stage_01-create_templates/templates/<image>/<vm_name>.yml.
    """

    model_config = _STRICT

    id: str = Field(pattern=C.IMAGE_RE.pattern)
    api_version: int = 1
    distro: str = Field(pattern=r"^[a-z0-9]+$", min_length=1)
    codename: str = Field(pattern=r"^[a-z0-9]+$", min_length=1)
    description: str = ""
    cloud_image: CloudImageSpec | None = None
    proxmox_templates: list[ProxmoxTemplateSpec] = Field(default_factory=list)


# --- box templates ---------------------------------------------------------

class BoxTemplate(BaseModel):
    """A VM/box archetype: role, OS, default inventory group, spec, attachments."""

    model_config = _STRICT

    id: str = Field(pattern=C.TEMPLATE_ID_RE.pattern)
    api_version: int = 1
    description: str = ""
    role: Literal["admin", "ctf", "team", "student", "template"]
    # Versioned base image the box clones, named ``<distro>_<codename>`` (e.g.
    # ``ubuntu_noble``, ``debian_trixie``) = the 01_init_proxmox templates/<image>/
    # set. Drives clone-image selection at authoring time (cpu/ram are clone-time
    # settings; the disk image carries the OS+version). The runtime role dispatch
    # still self-detects via ``ansible_facts.distribution``, so it agrees with the
    # cloned image. Defaults to ``ubuntu_noble`` (every existing box).
    image: str = Field(default="ubuntu_noble", pattern=C.IMAGE_RE.pattern)
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
