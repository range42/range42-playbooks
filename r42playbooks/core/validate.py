"""Semantic validation of a topology against itself and the catalog.

Schema-level constraints (patterns, ranges) are handled by the pydantic models.
This module covers cross-field semantics that pydantic cannot express alone:
referential integrity (zone->subnet, box->zone), IP-in-subnet, and dangling
catalog references. Returns a list of human-readable problems ([] == valid);
never raises.
"""

import ipaddress

from r42playbooks.core.catalog import Catalog
from r42playbooks.core.models import Topology


def zone_subnet_map(topology: Topology) -> dict[str, str]:
    """Map zone name -> subnet cidr (only for zones whose subnet exists)."""
    subnet_cidr = {s.name: s.cidr for s in topology.subnets}
    return {
        z.name: subnet_cidr[z.subnet]
        for z in topology.zones
        if z.subnet in subnet_cidr
    }


def zone_bridge_map(topology: Topology) -> dict[str, str]:
    """Map zone name -> bridge (only for zones whose subnet exists)."""
    subnet_bridge = {s.name: s.bridge for s in topology.subnets}
    return {
        z.name: subnet_bridge[z.subnet]
        for z in topology.zones
        if z.subnet in subnet_bridge
    }


def semantic_problems(topology: Topology, catalog: Catalog) -> list[str]:
    """Return human-readable semantic problems with a topology ([] if clean)."""
    problems: list[str] = []

    subnet_names = {s.name for s in topology.subnets}
    zone_names = {z.name for z in topology.zones}

    # zones must reference an existing subnet
    for z in topology.zones:
        if z.subnet not in subnet_names:
            problems.append(f"zone {z.name!r} references unknown subnet {z.subnet!r}")

    zsubnet = zone_subnet_map(topology)

    # boxes: zone must exist; ip must fall inside the zone's subnet
    for box in topology.boxes:
        if box.zone not in zone_names:
            problems.append(f"box {box.vm_name!r} references unknown zone {box.zone!r}")
            continue
        cidr = zsubnet.get(box.zone)
        if cidr is None:
            continue  # zone's subnet already reported missing
        try:
            net = ipaddress.ip_network(cidr, strict=True)
            if ipaddress.ip_address(box.ip) not in net:
                problems.append(
                    f"box {box.vm_name!r} ip {box.ip} not in zone {box.zone!r} subnet {cidr}"
                )
        except ValueError as exc:
            problems.append(f"box {box.vm_name!r}: {exc}")

        # box_template must resolve in the catalog
        if box.box_template not in catalog.box_templates:
            problems.append(
                f"box {box.vm_name!r} references unknown box_template {box.box_template!r}"
            )

    # network policy template must resolve
    if topology.network_policy.template not in catalog.network_policies:
        problems.append(
            f"unknown network_policy template {topology.network_policy.template!r}"
        )

    return problems
