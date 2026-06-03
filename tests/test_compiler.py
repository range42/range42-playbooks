"""P3 compiler tests (inventory, scenario_vms, network policy, stages, e2e)."""

import json

import pytest
import yaml

from r42topo.core.catalog import load_catalog
from r42topo.core.compiler import compile_topology
from r42topo.core.compiler.network_policy import compile_network_policy, lint_segmentation
from r42topo.core.idalloc import ReservedIndex
from r42topo.core.models import Topology


@pytest.fixture
def built(topology_factory, fake_catalog, reserved_factory, tmp_path):
    t = Topology.model_validate(topology_factory())
    cat = load_catalog(fake_catalog)
    reserved = ReservedIndex.from_file(reserved_factory([]))
    ws = tmp_path / "ws"
    result = compile_topology(t, workspace=ws, catalog=cat, reserved=reserved)
    return t, cat, result


# --- inventory ---

def test_inventory_structure(built):
    _, _, result = built
    inv = yaml.safe_load(result.inventory_path.read_text())
    groups = inv["all"]["children"]["range42_infrastructure"]["children"]
    assert "r42_admin_group" in groups
    assert "r42_vuln_box_group" in groups
    admin_hosts = groups["r42_admin_group"]["hosts"]
    assert "r42.admin-wazuh" in admin_hosts
    assert admin_hosts["r42.admin-wazuh"]["ansible_host"] == "192.168.142.100"


# --- scenario_vms manifest ---

def test_scenario_vms_manifest(built):
    _, _, result = built
    man = json.loads(result.scenario_vms_path.read_text())
    assert man["scenario"] == "demo_lab_network"
    by_name = {v["vm_name"]: v for v in man["vms"]}
    assert by_name["admin-wazuh"]["role"] == "admin"
    assert by_name["admin-wazuh"]["bridge"] == "vmbr142"
    assert by_name["vuln-box-00"]["role"] == "ctf"


# --- network policy compilation ---

def test_network_policy_ordered_rules(built):
    t, cat, _ = built
    pol = cat.network_policies["air-gap-ctf"]
    compiled = compile_network_policy(t, pol, version="1.1.0")
    weights = [r.weight for r in compiled.rules]
    assert weights == sorted(weights)  # emitted in ascending order

    # established first
    assert compiled.rules[0].ctstate and "ESTABLISHED" in compiled.rules[0].ctstate
    # admin -> ctf accept
    assert any(r.source == "192.168.142.0/24" and r.destination == "192.168.144.0/24"
               and r.jump == "ACCEPT" for r in compiled.rules)
    # ctf -> siem 1514/1515 accept
    siem = [r for r in compiled.rules if r.destination == "192.168.142.100" and r.jump == "ACCEPT"]
    assert {r.destination_port for r in siem} == {"1514", "1515"}
    # ctf -> admin drop
    assert any(r.source == "192.168.144.0/24" and r.destination == "192.168.142.0/24"
               and r.jump == "DROP" for r in compiled.rules)
    # air-gap: ctf bridge -> wan drop
    assert any(r.in_interface == "vmbr144" and r.jump == "DROP" and r.out_interface
               for r in compiled.rules)
    # terminal default-deny
    assert compiled.rules[-1].jump == "DROP"


def test_network_policy_deterministic(built):
    t, cat, _ = built
    pol = cat.network_policies["air-gap-ctf"]
    a = compile_network_policy(t, pol, version="1.1.0").model_dump_json()
    b = compile_network_policy(t, pol, version="1.1.0").model_dump_json()
    assert a == b


def test_segmentation_linter_passes_for_air_gap(built):
    t, cat, _ = built
    pol = cat.network_policies["air-gap-ctf"]
    compiled = compile_network_policy(t, pol, version="1.1.0")
    assert lint_segmentation(compiled, pol, t) == []


def test_segmentation_linter_flags_shadowed_drop(built):
    """An ACCEPT that precedes a same-pair DROP must be flagged (ordering hazard)."""
    t, cat, _ = built
    pol = cat.network_policies["air-gap-ctf"].model_copy(deep=True)
    # add ctf->admin ACCEPT before the existing ctf->admin DROP
    from r42topo.core.catalog_models import MatrixRule
    pol.matrix.insert(0, MatrixRule(src="ctf", dst="admin", action="accept",
                                    comment="bad: opens ctf->admin"))
    compiled = compile_network_policy(t, pol, version="1.1.0")
    assert lint_segmentation(compiled, pol, t) != []


# --- stages ---

def test_stages_merge_template_and_box_attachments(built):
    _, _, result = built
    stages = json.loads(result.stages_path.read_text())
    by_zone = {z["name"]: z for z in stages["zones"]}
    ctf_boxes = by_zone["ctf"]["boxes"]
    refs = [a["catalog_ref"] for a in ctf_boxes[0]["attachments"]]
    # template default for vuln-box includes the wazuh agent
    assert "software.install.wazuh-agent" in refs


# --- compile_topology orchestration ---

def test_compile_writes_all_artifacts(built):
    _, _, result = built
    for p in (result.topology_path, result.inventory_path,
              result.scenario_vms_path, result.network_policy_path, result.stages_path):
        assert p.exists()


def test_compile_topology_roundtrips_topology(built):
    t, _, result = built
    from r42topo.core.io import load_topology
    assert load_topology(result.topology_path) == t


def test_compile_rejects_allocation_conflict(topology_factory, fake_catalog,
                                             reserved_factory, tmp_path):
    from r42topo.core.errors import CompileError
    t = Topology.model_validate(topology_factory())
    cat = load_catalog(fake_catalog)
    reserved = ReservedIndex.from_file(reserved_factory([
        {"vm_id": 1100, "ip": "192.168.142.100", "scenario": "other", "role": "admin"},
    ]))
    with pytest.raises(CompileError):
        compile_topology(t, workspace=tmp_path / "ws2", catalog=cat, reserved=reserved)
