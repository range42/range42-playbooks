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
from r42playbooks.core.catalog import Catalog, find_template_vm
from r42playbooks.core.catalog_models import ProxmoxTemplateSpec
from r42playbooks.core.errors import CompileError, ValidationError
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.models import Attachment, Subnet
from r42playbooks.core.spec import BoxSpec, ScenarioSpec


@dataclass(frozen=True)
class ResolvedTemplate:
    """A concrete Proxmox template VM resolved from the catalog for this scenario.

    Contains only the template VMs actually referenced by boxes in the scenario
    (selective — not the full image table). The renderer uses this to emit only
    the needed ``stage_01-create_templates`` create plays.
    """

    vm_id: int
    vm_name: str
    spec: str
    ip: str
    bridge: str
    image: str   # image_id this template belongs to (e.g. "ubuntu_noble")


@dataclass(frozen=True)
class AllocatedBox:
    """One concrete VM: allocation result + everything the renderer needs."""

    vm_id: int
    vm_name: str
    ip: str
    bridge: str
    subnet_name: str
    section: str          # playbook directory (e.g. "02_admin_infrastructure")
    label: str            # human task label (e.g. "ADMIN INFRASTRUCTURE INIT")
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
    templates: tuple[ResolvedTemplate, ...]   # only the VMs this scenario actually needs
    subnets: tuple[Subnet, ...]


_DEFAULT_OCTET = 10  # starting octet for auto-allocated boxes (no explicit octet set)


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

    subnet_name = box.subnet
    subnet = subnets_by_name.get(subnet_name) if subnet_name else None
    if subnet is None:
        raise CompileError(
            f"subnet layout has no {subnet_name!r} subnet "
            f"(box {box.template!r})"
        )

    prefix = _subnet_prefix(subnet.cidr)

    # Resolve template VM from catalog (globally unique vm_name → image + spec).
    resolved = find_template_vm(catalog, bt.template_vm)
    if resolved is None:
        raise CompileError(
            f"box template {box.template!r} references unknown template_vm "
            f"{bt.template_vm!r} — add it to the catalog's 01_image_layer"
        )
    image_id, tpl_spec = resolved
    # BoxSpec.template_vm_id overrides the catalog reference for ad-hoc pinning.
    # image_id is kept from the catalog-resolved template_vm; only the numeric id changes.
    if box.template_vm_id is not None:
        tmpl_vm_id = box.template_vm_id
        tmpl_vm_name = bt.template_vm  # best-effort: catalog name may differ from override id
    else:
        tmpl_vm_id = tpl_spec.vm_id
        tmpl_vm_name = tpl_spec.vm_name

    attachments = tuple(bt.default_attachments) + tuple(box.attachments_add)
    start_octet = box.octet if box.octet is not None else _DEFAULT_OCTET

    placed: list[AllocatedBox] = []
    for name in _expand_names(box.template, box.count):
        octet = _next_free_octet(start_octet, prefix, taken_ips)
        vm_id = _next_free_vm_id(octet, taken_ids)
        ip = f"{prefix}.{octet}"
        taken_ips.add(ip)
        taken_ids.add(vm_id)
        placed.append(AllocatedBox(
            vm_id=vm_id,
            vm_name=name,
            ip=ip,
            bridge=subnet.bridge,
            subnet_name=subnet.name,
            section=subnet.section,
            label=subnet.label,
            gateway=subnet.gateway,
            inventory_group=f"r42_{subnet_name}_group",
            box_template=box.template,
            image=image_id,
            template_vm_id=tmpl_vm_id,
            template_name=tmpl_vm_name,
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

    # Resolve template subnet for IP/bridge derivation.
    tpl_subnet = layout.template_subnet
    if tpl_subnet is None:
        raise CompileError(
            f"subnet layout {spec.subnet_layout!r} has no template_subnet — add "
            f"template_subnet: {{cidr: '192.168.140.0/24', bridge: vmbr140}} to it"
        )
    tpl_prefix = _subnet_prefix(tpl_subnet.cidr)
    tpl_bridge = tpl_subnet.bridge

    # Build the deduplicated set of template VMs actually needed by this scenario.
    seen_tpl_ids: set[int] = set()
    resolved_templates: list[ResolvedTemplate] = []
    for box in boxes:
        if box.template_vm_id in seen_tpl_ids:
            continue
        result = find_template_vm(catalog, box.template_name)
        if result is None:
            continue  # template_vm_id override without catalog entry — skip manifest entry
        image_id, tpl_spec = result
        seen_tpl_ids.add(box.template_vm_id)
        resolved_templates.append(ResolvedTemplate(
            vm_id=tpl_spec.vm_id,
            vm_name=tpl_spec.vm_name,
            spec=tpl_spec.spec,
            ip=f"{tpl_prefix}.{tpl_spec.ip_octet}",
            bridge=tpl_bridge,
            image=image_id,
        ))

    return Allocation(
        scenario=spec.name,
        description=spec.notes,
        boxes=tuple(boxes),
        templates=tuple(sorted(resolved_templates, key=lambda t: t.vm_id)),
        subnets=tuple(layout.subnets),
    )


def manifest_dict(alloc: Allocation) -> dict[str, Any]:
    """Project an Allocation into the demo_lab ``scenario_vms.json`` dict."""
    vms = sorted(
        (
            {"vm_id": b.vm_id, "vm_name": b.vm_name, "ip": b.ip, "subnet": b.subnet_name,
             "bridge": b.bridge, "image": b.image}
            for b in alloc.boxes
        ),
        key=lambda v: v["vm_id"],
    )
    templates = sorted(
        [
            {"vm_id": t.vm_id, "vm_name": t.vm_name, "spec": t.spec, "ip": t.ip,
             "bridge": t.bridge, "image": t.image}
            for t in alloc.templates
        ],
        key=lambda t: t["vm_id"],
    )
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
