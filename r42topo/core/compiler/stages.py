"""Compile a topology into stages.json — the per-zone box/attachment dispatch.

This is the data the ``_universal`` Plan B playbook iterates: for each zone (in
deploy order), the boxes to create and, per box, the ordered catalog
attachments to apply. Each box's effective attachments are the box_template's
``default_attachments`` first, then the box's own ``attachments``, de-duplicated
by (kind, catalog_ref) keeping first occurrence.
"""

import json

from r42topo.core.catalog import Catalog
from r42topo.core.models import Box, Topology

# deploy order for zone roles (admin infra before students before ctf targets)
_ROLE_ORDER = {"template": 0, "admin": 1, "student": 2, "team": 3, "ctf": 4}


def _effective_attachments(box: Box, catalog: Catalog) -> list[dict]:
    template = catalog.box_templates.get(box.box_template)
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    source = list(template.default_attachments) if template else []
    source += list(box.attachments)
    for att in source:
        key = (att.kind, att.catalog_ref)
        if key in seen:
            continue
        seen.add(key)
        merged.append({"kind": att.kind, "catalog_ref": att.catalog_ref, "params": att.params})
    return merged


def build_stages(topology: Topology, catalog: Catalog) -> dict:
    """Return the stages dispatch as a plain dict."""
    zones_by_name = {z.name: z for z in topology.zones}
    boxes_by_zone: dict[str, list[Box]] = {}
    for box in topology.boxes:
        boxes_by_zone.setdefault(box.zone, []).append(box)

    ordered_zone_names = sorted(
        boxes_by_zone,
        key=lambda zn: (_ROLE_ORDER.get(zones_by_name[zn].role, 99), zn)
        if zn in zones_by_name else (99, zn),
    )

    zones_out = []
    for zname in ordered_zone_names:
        zone = zones_by_name.get(zname)
        zones_out.append({
            "name": zname,
            "role": zone.role if zone else None,
            "boxes": [
                {
                    "vm_name": box.vm_name,
                    "vm_id": box.vm_id,
                    "ip": box.ip,
                    "box_template": box.box_template,
                    "inventory_group": box.inventory_group,
                    "attachments": _effective_attachments(box, catalog),
                }
                for box in sorted(boxes_by_zone[zname], key=lambda b: b.vm_id)
            ],
        })

    return {"scenario": topology.scenario, "zones": zones_out}


def build_stages_json(topology: Topology, catalog: Catalog) -> str:
    """Serialize the stages dispatch as deterministic JSON."""
    return json.dumps(build_stages(topology, catalog), indent=2, sort_keys=True) + "\n"
