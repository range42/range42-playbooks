"""S5a renderer — class-(A) manifest-derived artifacts + frozen public API.

These files must reflect *this* composition (never copied from demo_lab):
``manifest/scenario_vms.json``, ``templates/ansible-inventory.j2`` (groups +
member hosts), ``templates/ssh-config.j2`` (a Host block per VM), and each
section's ``_main.yml`` (stage imports + per-VM ``global_*`` overrides). Also
asserts the frozen ``r42playbooks.api`` surface that gates S6 ∥ S7, and the M5
consistency invariant: every concrete stage ``hosts:`` resolves in the inventory.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

import r42playbooks.api as api
from r42playbooks.core.allocate import allocate
from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.render import render_scenario
from r42playbooks.core.spec import ScenarioSpec


@pytest.fixture
def rendered(fake_catalog, valid_spec_dict, tmp_path):
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    catalog = load_catalog(fake_catalog)
    alloc = allocate(spec, catalog)
    root = render_scenario(alloc, spec, catalog=catalog, dest=tmp_path / "scenarios")
    return spec, alloc, root


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


# --- manifest --------------------------------------------------------------

def test_manifest_written_with_vms_and_templates(rendered):
    _spec, alloc, root = rendered
    manifest = json.loads(_read(root, "manifest/scenario_vms.json"))
    vm_ids = {v["vm_id"] for v in manifest["vms"]}
    assert vm_ids == {b.vm_id for b in alloc.boxes}
    # H1: templates[] is populated (stage_00 global_template_vm_id depends on it)
    assert manifest["templates"], "templates[] must not be empty"
    assert manifest["scenario"] == alloc.scenario


# --- inventory (.j2) -------------------------------------------------------

def test_inventory_lists_composed_hosts_under_their_groups(rendered):
    _spec, _alloc, root = rendered
    inv = _read(root, "templates/ansible-inventory.j2")
    assert "r42_admin_group:" in inv
    assert "r42_vuln_box_group:" in inv
    assert "r42.admin-wazuh:" in inv
    assert "r42.vuln-box-00:" in inv
    assert "r42.vuln-box-04:" in inv
    assert "proxmox:" in inv and "proxmox-cli:" in inv


def test_inventory_excludes_demo_lab_specific_hosts(rendered):
    """Class-A files reflect THIS composition, not demo_lab's 10 VMs."""
    _spec, _alloc, root = rendered
    inv = _read(root, "templates/ansible-inventory.j2")
    for ghost in ("student-box-01", "init-vm", "deployer", "builder"):
        assert ghost not in inv


def test_inventory_is_valid_yaml_when_jinja_neutralised(rendered):
    """The .j2 is YAML-shaped (Jinja only in proxmox host values)."""
    _spec, _alloc, root = rendered
    inv = _read(root, "templates/ansible-inventory.j2")
    neutral = re.sub(r"\{\{.*?\}\}", "PLACEHOLDER", inv)
    data = yaml.safe_load(neutral)
    groups = data["all"]["children"]["range42_infrastructure"]["children"]
    assert "r42_admin_group" in groups and "r42_vuln_box_group" in groups


# --- ssh-config (.j2) ------------------------------------------------------

def test_ssh_config_has_one_block_per_vm(rendered):
    _spec, alloc, root = rendered
    ssh = _read(root, "templates/ssh-config.j2")
    for box in alloc.boxes:
        assert f"Host r42.{box.vm_name}\n    Hostname {box.ip}" in ssh
    assert "192.168.143.160" not in ssh  # demo_lab student box IP


# --- section _main.yml -----------------------------------------------------

def test_section_main_imports_stages_with_global_vars(rendered):
    _spec, alloc, root = rendered
    main = _read(root, "04_ctf_infrastructure/_main.yml")
    assert "- import_playbook: ./stage_00/vuln-box-00.yml" in main
    assert "- import_playbook: ./stage_01/vuln-box-00.yml" in main
    vb0 = next(b for b in alloc.boxes if b.vm_name == "vuln-box-00")
    assert f"global_vm_id: {vb0.vm_id}" in main
    assert f'global_vm_ci_ip: "{vb0.ip}"' in main
    assert f"global_template_vm_id: {vb0.template_vm_id}" in main
    assert 'global_vm_ssh_name: "r42.vuln-box-00"' in main


def test_section_main_is_valid_yaml(rendered):
    _spec, _alloc, root = rendered
    for section in ("02_admin_infrastructure", "04_ctf_infrastructure"):
        docs = list(yaml.safe_load_all(_read(root, f"{section}/_main.yml")))
        plays = [d for d in docs if d]
        assert plays, f"{section}/_main.yml parsed empty"


# --- M5 consistency invariant ---------------------------------------------

def test_every_stage01_host_resolves_in_inventory(rendered):
    """Golden-assert: each concrete `hosts: r42.<x>` exists in the inventory."""
    _spec, _alloc, root = rendered
    inv = _read(root, "templates/ansible-inventory.j2")
    host_lines = set(re.findall(r"^\s*(r42\.[a-z0-9-]+):\s*$", inv, re.MULTILINE))
    for stage01 in root.rglob("stage_01/*.yml"):
        for host in re.findall(r"hosts:\s*(r42\.[a-z0-9-]+)", stage01.read_text()):
            assert host in host_lines, f"{stage01.name}: {host} missing from inventory"


# --- frozen public API -----------------------------------------------------

def test_api_render_scenario_signature_and_output(fake_catalog, valid_spec_dict, tmp_path):
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    catalog = load_catalog(fake_catalog)
    root = api.render_scenario(spec, catalog=catalog, dest=tmp_path / "out")
    assert isinstance(root, Path)
    assert root.is_dir()
    assert (root / "manifest" / "scenario_vms.json").is_file()
    assert (root / "templates" / "ansible-inventory.j2").is_file()


def test_api_exposes_frozen_surface():
    for name in ("render_scenario", "allocate", "load_spec", "load_catalog",
                 "list_roles", "list_containers", "validate_refs", "ScenarioSpec"):
        assert hasattr(api, name), f"api.{name} missing (frozen surface)"
