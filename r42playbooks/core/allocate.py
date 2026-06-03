"""Turn a ``ScenarioSpec`` into a concrete, deterministic VM allocation.

Renderer-A of the generator: place each composed box in its role's subnet,
assign a ``vm_id``/IP that honours the project **octet rule** (vm_id last 3
digits == IP last octet for single-subnet VMs) and **global uniqueness** via
``_reserved.json``, resolve each box's Proxmox clone template (§7.1 / H2),
expand ``count>1`` boxes, and emit the demo_lab ``scenario_vms.json`` shape with
a populated ``templates[]`` (H1).

Pure and read-only: it never writes ``_reserved.json`` (claiming reservations
with a lock is the deploy side's job — see ``idalloc`` docstring).
"""

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from r42playbooks.core import constants as C
from r42playbooks.core.catalog import Catalog
from r42playbooks.core.errors import CompileError
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.models import Attachment, Subnet
from r42playbooks.core.spec import BoxSpec, ScenarioSpec
from r42playbooks.core.templates_table import TEMPLATE_TABLE, ProxmoxTemplate, select_template


@dataclass(frozen=True)
class AllocatedBox:
    """One concrete VM: allocation result + everything the renderer needs."""

    vm_id: int
    vm_name: str
    ip: str
    role: str
    bridge: str
    subnet_name: str
    gateway: str | None
    inventory_group: str
    box_template: str           # the catalog box-template id (e.g. "vuln-box")
    image: str                  # versioned base image (e.g. ubuntu_noble, debian_trixie)
    template_vm_id: int         # the 9xxx clone source (global_template_vm_id)
    template_name: str
    attachments: tuple[Attachment, ...]
    box_vars: Mapping[str, Any]   # read-only (MappingProxyType) — frozen-dataclass safe


@dataclass(frozen=True)
class Allocation:
    """The fully-resolved composition the renderer turns into a scenario tree."""

    scenario: str
    description: str
    boxes: tuple[AllocatedBox, ...]
    templates: tuple[ProxmoxTemplate, ...]
    subnets: tuple[Subnet, ...]


def _subnet_prefix(cidr: str) -> str:
    """Return the leading 3 octets of a /24 CIDR (host octet stripped)."""
    return cidr.split("/", 1)[0].rsplit(".", 1)[0]


def _expand_names(template_id: str, count: int) -> list[str]:
    """count==1 -> bare template id; count>1 -> template-00..0(count-1)."""
    if count == 1:
        return [template_id]
    return [f"{template_id}-{i:0{C.REPLICA_PAD}d}" for i in range(count)]


def _next_free_octet(base: int, prefix: str, taken_ips: set[str]) -> int:
    """Lowest host octet >= base whose IP in *prefix* is not already taken."""
    for octet in range(base, C.HOST_OCTET_MAX + 1):
        if f"{prefix}.{octet}" not in taken_ips:
            return octet
    raise CompileError(f"subnet {prefix}.0/24 exhausted from octet {base}")


def _next_free_vm_id(octet: int, taken_ids: set[int]) -> int:
    """Lowest vm_id (band*1000+octet, bands 1..8) not already claimed.

    Every candidate satisfies the octet rule by construction (vm_id % 1000 ==
    octet); bumping the band keeps the rule while dodging a global collision.
    """
    for band in range(C.VM_ID_BAND_MIN, C.VM_ID_BAND_MAX + 1):
        vm_id = band * 1000 + octet
        if vm_id not in taken_ids:
            return vm_id
    raise CompileError(f"no free vm_id band for octet {octet} (bands 1..{C.VM_ID_BAND_MAX} taken)")


def _blocked(reserved: ReservedIndex, scenario: str) -> tuple[set[int], set[str]]:
    """vm_ids/IPs owned by *other* scenarios (our own rows do not block a re-run)."""
    ids = {int(e["vm_id"]) for e in reserved.entries
           if "vm_id" in e and e.get("scenario") != scenario}
    ips = {str(e["ip"]) for e in reserved.entries
           if "ip" in e and e.get("scenario") != scenario}
    return ids, ips


def _allocate_box(
    box: BoxSpec,
    catalog: Catalog,
    subnets_by_name: dict[str, Subnet],
    spec_name: str,
    taken_ids: set[int],
    taken_ips: set[str],
) -> list[AllocatedBox]:
    """Resolve and place every replica of one composed box."""
    bt = catalog.resolve_box_template(box.template)  # raises CatalogNotFoundError
    if bt.role == "template":
        raise CompileError(f"box template {box.template!r} has role 'template' and is not placeable")

    subnet_name = C.ROLE_SUBNET_NAME.get(bt.role)
    subnet = subnets_by_name.get(subnet_name) if subnet_name else None
    if subnet is None:
        raise CompileError(
            f"subnet layout has no {subnet_name!r} subnet for role {bt.role!r} "
            f"(box {box.template!r})"
        )

    prefix = _subnet_prefix(subnet.cidr)
    tmpl = select_template(bt.spec, image=bt.image, override_vm_id=box.template_vm_id)
    attachments = tuple(bt.default_attachments) + tuple(box.attachments_add)
    base_octet = C.ROLE_BASE_OCTET[bt.role]

    placed: list[AllocatedBox] = []
    for name in _expand_names(box.template, box.count):
        octet = _next_free_octet(base_octet, prefix, taken_ips)
        vm_id = _next_free_vm_id(octet, taken_ids)
        ip = f"{prefix}.{octet}"
        taken_ips.add(ip)
        taken_ids.add(vm_id)
        placed.append(AllocatedBox(
            vm_id=vm_id,
            vm_name=name,
            ip=ip,
            role=bt.role,
            bridge=subnet.bridge,
            subnet_name=subnet.name,
            gateway=subnet.gateway,
            inventory_group=bt.default_inventory_group,
            box_template=box.template,
            image=bt.image,
            template_vm_id=tmpl.vm_id,
            template_name=tmpl.vm_name,
            attachments=attachments,
            box_vars=MappingProxyType(dict(box.vars)),
        ))
    return placed


def allocate(spec: ScenarioSpec, catalog: Catalog, reserved: ReservedIndex | None = None) -> Allocation:
    """Resolve *spec* against *catalog* into a deterministic ``Allocation``.

    :raises CatalogNotFoundError: a referenced subnet layout / box template is unknown.
    :raises CompileError: a box cannot be placed (no subnet, exhausted ids/octets).
    """
    if reserved is None:
        reserved = ReservedIndex(entries=())

    layout = catalog.resolve_subnet_layout(spec.subnet_layout)
    subnets_by_name = {s.name: s for s in layout.subnets}

    taken_ids, taken_ips = _blocked(reserved, spec.name)

    boxes: list[AllocatedBox] = []
    for box in spec.boxes:
        boxes.extend(
            _allocate_box(box, catalog, subnets_by_name, spec.name, taken_ids, taken_ips)
        )

    return Allocation(
        scenario=spec.name,
        description=spec.notes,
        boxes=tuple(boxes),
        templates=TEMPLATE_TABLE,
        subnets=tuple(layout.subnets),
    )


def manifest_dict(alloc: Allocation) -> dict[str, Any]:
    """Project an Allocation into the demo_lab ``scenario_vms.json`` dict."""
    vms = sorted(
        (
            {"vm_id": b.vm_id, "vm_name": b.vm_name, "ip": b.ip, "role": b.role,
             "bridge": b.bridge, "image": b.image}
            for b in alloc.boxes
        ),
        key=lambda v: v["vm_id"],
    )
    templates = [
        {"vm_id": t.vm_id, "vm_name": t.vm_name, "spec": t.spec, "ip": t.ip,
         "bridge": t.bridge, "image": t.image}
        for t in alloc.templates
    ]
    return {
        "scenario": alloc.scenario,
        "version": 2,
        "description": alloc.description,
        "vms": vms,
        "templates": templates,
    }


def manifest_json(alloc: Allocation) -> str:
    """Serialize the manifest as deterministic, sorted JSON."""
    return json.dumps(manifest_dict(alloc), indent=2, sort_keys=True) + "\n"
