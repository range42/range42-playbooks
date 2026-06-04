"""Generate a starter Topology from catalog templates (pure, reused by CLI + TUI).

``scaffold_topology`` turns a subnet-layout + policy choice into a minimal,
valid, deployable topology: one zone per subnet and one box per zone whose
template id best matches the subnet name. vm_id/IP are auto-assigned to satisfy
the project octet rule (vm_id last 3 digits == IP last octet). The result is a
starting point an operator refines in the CLI/TUI.
"""

import ipaddress

from r42playbooks.core.catalog import Catalog
from r42playbooks.core.errors import ValidationError
from r42playbooks.core.models import Box, NetworkPolicyRef, Topology, Zone

# subnet name -> default last-octet for the first box in that zone
_SUBNET_OCTET = {"admin": 100, "ctf": 170, "student": 160}
_DEFAULT_OCTET = 200

# Subnet names to skip (infrastructure subnets, not lab zones)
_SKIP_SUBNETS = {"template"}


def _first_template_for_subnet(catalog: Catalog, subnet_name: str, used: set):
    """Pick the best-matching unused box template for *subnet_name*.

    Preference order:
    1. template id starts with the subnet name (e.g. "admin-wazuh" for "admin")
    2. template id contains the subnet name
    3. alphabetically first unused template (fallback)
    """
    candidates = [t for t in catalog.box_templates.values() if t.id not in used]
    if not candidates:
        return None
    # prefer id starts with subnet_name
    for t in sorted(candidates, key=lambda x: x.id):
        if t.id.startswith(subnet_name):
            return t
    # then prefer id contains subnet_name
    for t in sorted(candidates, key=lambda x: x.id):
        if subnet_name in t.id:
            return t
    # fallback: alphabetically first unused
    return sorted(candidates, key=lambda x: x.id)[0]


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

    zones, boxes = [], []
    subnet_seen: dict[str, int] = {}  # per-subnet count -> distinct octet/vm_id per box
    used_templates: set = set()  # track globally-used template ids for uniqueness

    for subnet in layout.subnets:
        # Use subnet.base_octet if set, else fall back to legacy name-based table
        base = subnet.base_octet if subnet.base_octet else _SUBNET_OCTET.get(subnet.name, _DEFAULT_OCTET)
        role = subnet.name if subnet.name in ("admin", "ctf", "student", "team") else "team"
        zones.append(Zone(name=subnet.name, subnet=subnet.name, role=role))
        if subnet.name in _SKIP_SUBNETS:
            continue
        template = _first_template_for_subnet(catalog, subnet.name, used_templates)
        if template is None:
            continue  # no archetype for this subnet — leave the zone box-less
        used_templates.add(template.id)
        nth = subnet_seen.get(subnet.name, 0)
        subnet_seen[subnet.name] = nth + 1
        octet = base + nth  # avoid dup vm_id/IP per subnet
        boxes.append(Box(
            vm_name=f"{template.id}-{nth:02d}" if nth else template.id,
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
        subnets=list(layout.subnets),  # pydantic accepts model instances directly
        zones=zones,
        boxes=boxes,
        network_policy=NetworkPolicyRef(template=policy_id),
    )
