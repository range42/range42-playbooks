"""Compile a topology into an Ansible YAML inventory (hosts.yml).

Reproduces range42's nested layout::

    all.children.range42_infrastructure.children.<group>.hosts.r42.<vm_name>

Only the scenario's VM groups are emitted; the ``proxmox`` / ``proxmox-cli``
host groups are workspace-level (provided by the deployer base inventory), so
the host-level network-policy play targets those, merged at deploy time.

Group names come from each box's validated ``inventory_group`` (snake_case);
host keys are ``r42.<vm_name>``. Emitted via ``yaml.safe_dump`` — topology
strings are data, never templated, so there is no SSTI surface.
"""

import yaml

from r42playbooks.core.models import Topology


def build_inventory(topology: Topology) -> dict:
    """Return the inventory as a plain dict (groups -> hosts -> host vars)."""
    groups: dict[str, dict] = {}
    zone_role = {z.name: z.role for z in topology.zones}

    for box in topology.boxes:
        group = groups.setdefault(box.inventory_group, {"hosts": {}})
        group["hosts"][f"r42.{box.vm_name}"] = {
            "ansible_host": box.ip,
            "r42_vm_id": box.vm_id,
            "r42_vm_name": box.vm_name,
            "r42_zone": box.zone,
            "r42_role": zone_role.get(box.zone),
        }

    return {
        "all": {
            "children": {
                "range42_infrastructure": {
                    "children": {name: groups[name] for name in sorted(groups)},
                },
            },
        },
    }


def build_inventory_yaml(topology: Topology) -> str:
    """Serialize the inventory as deterministic YAML."""
    return yaml.safe_dump(build_inventory(topology), sort_keys=True, default_flow_style=False)
