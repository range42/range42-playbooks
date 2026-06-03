"""Shared test fixtures for r42playbooks."""

import copy

import pytest


@pytest.fixture
def valid_topology_dict() -> dict:
    """A minimal, valid topology spec (admin + ctf zones, one box each)."""
    return {
        "schema_version": 1,
        "scenario": "demo_lab_network",
        "description": "test topology",
        "proxmox_node": "px-testing",
        "subnets": [
            {"name": "admin", "cidr": "192.168.142.0/24", "bridge": "vmbr142",
             "gateway": "192.168.142.1"},
            {"name": "ctf", "cidr": "192.168.144.0/24", "bridge": "vmbr144"},
        ],
        "zones": [
            {"name": "admin", "subnet": "admin", "role": "admin"},
            {"name": "ctf", "subnet": "ctf", "role": "ctf"},
        ],
        "boxes": [
            {"vm_name": "admin-wazuh", "vm_id": 1100, "ip": "192.168.142.100",
             "zone": "admin", "box_template": "admin-wazuh",
             "inventory_group": "r42_admin_group",
             "attachments": [
                 {"kind": "role", "catalog_ref": "software.install.wazuh", "params": {}},
             ]},
            {"vm_name": "vuln-box-00", "vm_id": 1170, "ip": "192.168.144.170",
             "zone": "ctf", "box_template": "vuln-box",
             "inventory_group": "r42_vuln_box_group", "attachments": []},
        ],
        "network_policy": {"template": "air-gap-ctf", "overrides": {}},
    }


@pytest.fixture
def valid_spec_dict() -> dict:
    """A minimal, valid scenario.r42.yml composition spec (msfvenom 'options')."""
    return {
        "schema_version": 1,
        "name": "my_lab",
        "subnet_layout": "default-3zone",
        "network_policy": "air-gap-ctf",
        "proxmox_node": "px-testing",
        "notes": "demo composition",
        "boxes": [
            {"template": "admin-wazuh"},
            {
                "template": "vuln-box",
                "count": 5,
                "attachments_add": [
                    {"kind": "role", "catalog_ref": "software.install.extra", "params": {}},
                ],
                "vars": {"difficulty": "hard"},
            },
        ],
    }


@pytest.fixture
def spec_factory(valid_spec_dict):
    """Return a deep-copy mutator so tests can tweak one spec field in isolation."""
    def _make(**overrides) -> dict:
        spec = copy.deepcopy(valid_spec_dict)
        spec.update(overrides)
        return spec
    return _make


@pytest.fixture
def topology_factory(valid_topology_dict):
    """Return a deep-copy mutator so tests can tweak one field in isolation."""
    def _make(**overrides) -> dict:
        spec = copy.deepcopy(valid_topology_dict)
        spec.update(overrides)
        return spec
    return _make


def _write(path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def fake_catalog(tmp_path):
    """Materialize a minimal, valid 05_topology_layer catalog under tmp_path.

    Returns the catalog_root (the dir that *contains* 05_topology_layer),
    mirroring how range42-catalog is laid out on disk.
    """
    root = tmp_path / "range42-catalog"
    layer = root / "05_topology_layer"

    _write(layer / "subnet_layouts" / "default-3zone" / "v1.0.0" / "template.yml", """
id: default-3zone
api_version: 1
description: admin + ctf + student subnets
subnets:
  - {name: admin, cidr: "192.168.142.0/24", bridge: vmbr142, gateway: "192.168.142.1"}
  - {name: ctf, cidr: "192.168.144.0/24", bridge: vmbr144}
  - {name: student, cidr: "192.168.143.0/24", bridge: vmbr143}
""".lstrip())

    _write(layer / "box_templates" / "vuln-box" / "v1.0.0" / "template.yml", """
id: vuln-box
api_version: 1
description: CTF vulnerable target
role: ctf
default_inventory_group: r42_vuln_box_group
spec: "1cpu/4gb/32gb"
default_attachments:
  - {kind: role, catalog_ref: software.install.wazuh-agent, params: {}}
""".lstrip())

    _write(layer / "box_templates" / "admin-wazuh" / "v1.0.0" / "template.yml", """
id: admin-wazuh
api_version: 1
description: Wazuh SIEM admin box
role: admin
default_inventory_group: r42_admin_group
spec: "4cpu/8gb/64gb"
""".lstrip())

    # two versions of a policy — loader must pick the highest (1.1.0)
    for ver, comment in (("v1.0.0", "v1"), ("v1.1.0", "v1.1")):
        _write(layer / "network_policies" / "air-gap-ctf" / ver / "template.yml", f"""
id: air-gap-ctf
api_version: 1
kind: isolation-policy
description: admin/ctf isolation + ctf air-gap ({comment})
params:
  siem_ip: "192.168.142.100"
zones:
  - {{name: admin}}
  - {{name: ctf}}
  - {{name: wan, wan: true}}
services:
  - {{name: siem, zone: admin, ports: [{{proto: tcp, port: 1514}}, {{proto: tcp, port: 1515}}]}}
defaults:
  default_action: drop
  accept_established_related: true
  allow_intra_zone: true
  airgap_zones: [ctf]
matrix:
  - {{src: admin, dst: ctf, action: accept, comment: "admin manages vuln boxes"}}
  - {{src: ctf, dst: "svc:siem", action: accept, comment: "wazuh agent"}}
  - {{src: ctf, dst: admin, action: drop, comment: "zone isolation"}}
""".lstrip())

    return root


@pytest.fixture
def reserved_factory(tmp_path):
    """Write a JSONL _reserved.json (one object per line) from a list of dicts."""
    import json

    def _make(entries: list[dict]) -> "object":
        from pathlib import Path
        path = Path(tmp_path) / "_reserved.json"
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        return path
    return _make
