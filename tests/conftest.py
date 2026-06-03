"""Shared test fixtures for r42topo."""

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
def topology_factory(valid_topology_dict):
    """Return a deep-copy mutator so tests can tweak one field in isolation."""
    def _make(**overrides) -> dict:
        spec = copy.deepcopy(valid_topology_dict)
        spec.update(overrides)
        return spec
    return _make
