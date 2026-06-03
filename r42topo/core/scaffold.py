"""Generate a starter Topology from catalog templates (pure, reused by CLI + TUI).

``scaffold_topology`` turns a subnet-layout + policy choice into a minimal,
valid, deployable topology: one zone per subnet and one box per zone whose role
has a matching box_template. vm_id/IP are auto-assigned to satisfy the project
octet rule (vm_id last 3 digits == IP last octet). The result is a starting
point an operator refines in the CLI/TUI.
"""

import ipaddress

from r42topo.core.catalog import Catalog
from r42topo.core.errors import ValidationError
from r42topo.core.models import Box, NetworkPolicyRef, Topology, Zone

# subnet/zone name -> role (anything unrecognized becomes a team zone)
_NAME_ROLE = {"admin": "admin", "ctf": "ctf", "student": "student", "template": "template"}
# role -> default last-octet for the first box in that zone
_ROLE_OCTET = {"admin": 100, "ctf": 170, "student": 160, "team": 200}


def _role_for(subnet_name: str) -> str:
    return _NAME_ROLE.get(subnet_name, "team")


def _first_template_for_role(catalog: Catalog, role: str):
    for template in catalog.box_templates.values():
        if template.role == role:
            return template
    return None


def _ip_with_octet(cidr: str, octet: int) -> str:
    net = ipaddress.ip_network(cidr, strict=True)
    base = str(net.network_address).rsplit(".", 1)[0]
    return f"{base}.{octet}"


def scaffold_topology(
    catalog: Catalog,
    *,
    scenario: str,
    layout_id: str,
    policy_id: str,
    proxmox_node: str = "px-testing",
    description: str = "",
) -> Topology:
    """Build a minimal valid Topology from a subnet layout + network policy.

    :raises ValidationError: if no box template matches any zone role.
    """
    layout = catalog.resolve_subnet_layout(layout_id)
    catalog.resolve_network_policy(policy_id)  # fail fast if missing

    subnets = [s.model_dump() for s in layout.subnets]
    zones, boxes = [], []

    for subnet in layout.subnets:
        role = _role_for(subnet.name)
        zones.append(Zone(name=subnet.name, subnet=subnet.name, role=role))
        if role == "template":
            continue
        template = _first_template_for_role(catalog, role)
        if template is None:
            continue  # no archetype for this role — leave the zone box-less
        octet = _ROLE_OCTET.get(role, 200)
        boxes.append(Box(
            vm_name=template.id,
            vm_id=1000 + octet,
            ip=_ip_with_octet(subnet.cidr, octet),
            zone=subnet.name,
            box_template=template.id,
            inventory_group=template.default_inventory_group,
        ))

    if not boxes:
        raise ValidationError(
            f"layout {layout_id!r} produced no boxes — no box template matched any zone role"
        )

    return Topology(
        scenario=scenario,
        description=description,
        proxmox_node=proxmox_node,
        subnets=subnets,
        zones=zones,
        boxes=boxes,
        network_policy=NetworkPolicyRef(template=policy_id),
    )
