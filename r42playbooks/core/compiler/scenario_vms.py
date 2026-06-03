"""Compile a topology into manifest/scenario_vms.json (the demo_lab shape).

range42-context reads this manifest to know a scenario's VMs (e.g. to flush
their SSH known_hosts on redeploy). Role comes from the box's zone; bridge
comes from the zone's subnet. Templates (the 9xxx clone sources) are not part
of a topology and are emitted as an empty list for now.
"""

import json

from r42playbooks.core.models import Topology
from r42playbooks.core.validate import zone_bridge_map


def build_scenario_vms(topology: Topology) -> dict:
    """Return the scenario_vms manifest as a plain dict."""
    zone_role = {z.name: z.role for z in topology.zones}
    zbridge = zone_bridge_map(topology)

    vms = sorted(
        (
            {
                "vm_id": box.vm_id,
                "vm_name": box.vm_name,
                "ip": box.ip,
                "role": zone_role.get(box.zone),
                "bridge": zbridge.get(box.zone),
            }
            for box in topology.boxes
        ),
        key=lambda v: v["vm_id"],
    )

    return {
        "scenario": topology.scenario,
        "version": 2,
        "description": topology.description,
        "vms": vms,
        "templates": [],
    }


def build_scenario_vms_json(topology: Topology) -> str:
    """Serialize the manifest as deterministic JSON."""
    return json.dumps(build_scenario_vms(topology), indent=2, sort_keys=True) + "\n"
