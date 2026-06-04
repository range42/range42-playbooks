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
template_subnet: {cidr: "192.168.140.0/24", bridge: vmbr140}
""".lstrip())

    _write(layer / "box_templates" / "vuln-box" / "v1.0.0" / "template.yml", """
id: vuln-box
api_version: 1
description: CTF vulnerable target
role: ctf
template_vm: "template-vm-ubuntu-noble-small-01-4g-32g"
default_inventory_group: r42_vuln_box_group
default_attachments:
  - {kind: role, catalog_ref: software.install.wazuh-agent, params: {}}
""".lstrip())

    _write(layer / "box_templates" / "admin-wazuh" / "v1.0.0" / "template.yml", """
id: admin-wazuh
api_version: 1
description: Wazuh SIEM admin box
role: admin
template_vm: "template-vm-ubuntu-noble-medium-04-8g-64g"
default_inventory_group: r42_admin_group
""".lstrip())

    _write(layer / "box_templates" / "student-box" / "v1.0.0" / "template.yml", """
id: student-box
api_version: 1
description: student workstation
role: student
template_vm: "template-vm-ubuntu-noble-micro-01-2g-24g"
default_inventory_group: r42_student_group
""".lstrip())

    # 02_ansible_layer: reusable roles, referenced by name (<category>.<action>.<target>).
    for role in ("software.install.wazuh", "software.install.wazuh-agent", "software.install.extra"):
        _write(root / "02_ansible_layer" / "admin" / "roles" / role / "tasks" / "main.yml", "---\n[]\n")

    # 03_container_layer: CTF docker stacks, referenced by path under _ctf/.
    _write(root / "03_container_layer" / "docker" / "_ctf" / "cve" / "web" / "dvwa" / "docker-compose.yml",
           "services: {}\n")
    _write(root / "03_container_layer" / "docker" / "_ctf" / "misconfiguration" / "network" / "open-smb" / "compose.yml",
           "services: {}\n")

    # 01_image_layer: base VM image descriptors (ubuntu_noble + debian_trixie)
    _write(root / "01_image_layer" / "ubuntu_noble" / "v1.0.0" / "image.yml", """
id: ubuntu_noble
api_version: 1
distro: ubuntu
codename: noble
description: Ubuntu 24.04 LTS (Noble Numbat)
cloud_image:
  url: "https://cloud-images.ubuntu.com/minimal/daily/noble/current/noble-minimal-cloudimg-amd64.img"
  filename: "noble-minimal-cloudimg-amd64.img"
proxmox_templates:
  - {vm_id: 9211, vm_name: "template-vm-ubuntu-noble-micro-01-2g-24g",  spec: "1cpu/2gb/24gb", ip_octet: 211}
  - {vm_id: 9221, vm_name: "template-vm-ubuntu-noble-small-01-4g-32g",  spec: "1cpu/4gb/32gb", ip_octet: 221}
  - {vm_id: 9232, vm_name: "template-vm-ubuntu-noble-medium-02-8g-64g", spec: "2cpu/8gb/64gb", ip_octet: 232}
  - {vm_id: 9234, vm_name: "template-vm-ubuntu-noble-medium-04-8g-64g", spec: "4cpu/8gb/64gb", ip_octet: 234}
""".lstrip())
    _write(root / "01_image_layer" / "debian_trixie" / "v1.0.0" / "image.yml", """
id: debian_trixie
api_version: 1
distro: debian
codename: trixie
description: Debian 13 (Trixie)
cloud_image:
  url: "https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.raw"
  filename: "debian-13-genericcloud-amd64.img"
proxmox_templates:
  - {vm_id: 9321, vm_name: "template-vm-debian-trixie-small",  spec: "1cpu/4gb/32gb", ip_octet: 121}
  - {vm_id: 9331, vm_name: "template-vm-debian-trixie-medium", spec: "2cpu/8gb/64gb", ip_octet: 131}
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
