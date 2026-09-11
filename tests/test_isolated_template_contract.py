"""Ownership and success proofs for an isolated Noble template build."""

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILTER = (
    ROOT
    / "bundles/proxmox/template.build.ubuntu_noble/filter_plugins/isolated_template.py"
)


@pytest.fixture
def contract():
    assert FILTER.is_file(), (
        "The isolated builder must validate its explicit contract before writes"
    )
    spec = importlib.util.spec_from_file_location("isolated_template", FILTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plan():
    return {
        "build_id": "a" * 32,
        "vm_id": 62000,
        "name": "r42-template-test",
        "node": "pve01",
        "image_path": "/var/lib/vz/template/iso/r42-noble-a.img",
        "image_sha256": "b" * 64,
        "disk_storage": "local-lvm",
        "snippet_storage": "local",
        "disk_gb": 16,
        "cores": 1,
        "memory_mb": 1024,
        "bridge": "r42smk",
        "address": "10.42.70.30/24",
        "gateway": "10.42.70.1",
        "dns": ["1.1.1.1"],
        "guest_host": "r42-template-test",
    }


def test_plan_is_literal_and_binds_every_mutable_field(contract, plan):
    original = copy.deepcopy(plan)
    result = contract.template_plan(plan)
    assert plan == original
    assert result["ip"] == "10.42.70.30" and result["prefix"] == 24
    assert result["description"].startswith(
        "range42-template-build:" + "a" * 32 + "\nrange42-template-plan:"
    )
    changed = {**plan, "memory_mb": 2048}
    assert contract.template_plan(changed)["description"] != result["description"]


@pytest.mark.parametrize(
    "changes",
    [
        {"vm_id": 9901},
        {"vm_id": True},
        {"build_id": "../unsafe"},
        {"name": "bad;command"},
        {"node": "pve01\nother"},
        {"image_path": "/tmp/a;cmd"},
        {"image_path": "/var/../tmp/image"},
        {"image_sha256": "missing"},
        {"disk_storage": "a/b"},
        {"memory_mb": 0},
        {"cores": True},
        {"address": "10.42.70.0/24"},
        {"address": "10.42.70.255/24"},
        {"gateway": "10.42.71.1"},
        {"address": "{{ target }}"},
        {"guest_host": "all"},
        {"guest_host": "x:y"},
        {"apt_proxy_url": "http://user:secret@example.org"},
        {"unexpected": True},
    ],
)
def test_invalid_or_unsupported_plan_fails_before_mutation(contract, plan, changes):
    with pytest.raises(ValueError):
        contract.template_plan({**plan, **changes})


def test_resume_requires_exact_plan_name_marker_and_node(contract, plan):
    normalized = contract.template_plan(plan)
    config = {
        "name": plan["name"],
        "description": normalized["description"],
        "template": 0,
    }
    assert contract.template_owned(config, normalized, "pve01")
    for changes in (
        {"name": "foreign"},
        {"description": normalized["description"] + "suffix"},
        {"template": 1},
    ):
        with pytest.raises(ValueError):
            contract.template_owned({**config, **changes}, normalized, "pve01")
    with pytest.raises(ValueError):
        contract.template_owned(config, normalized, "different-node")


def test_stopped_state_alone_is_not_a_success_proof(contract, plan):
    normalized = contract.template_plan(plan)
    with pytest.raises(ValueError):
        contract.template_success({"status": "stopped"}, normalized)


def test_success_proof_requires_current_build_and_package_consistency(contract, plan):
    normalized = contract.template_plan(plan)
    proof = {
        "version": 1,
        "build_id": plan["build_id"],
        "plan_sha256": normalized["plan_sha256"],
        "cloud_init": "done",
        "package_audit": "clean",
        "package_module": "completed",
    }
    assert contract.template_success(proof, normalized)
    for changes in (
        {"build_id": "c" * 32},
        {"plan_sha256": "c" * 64},
        {"cloud_init": "degraded done"},
        {"package_audit": "unavailable"},
        {"package_module": "missing"},
    ):
        with pytest.raises(ValueError):
            contract.template_success({**proof, **changes}, normalized)


def test_active_resume_requires_unchanged_disk_network_resources_and_bootstrap(
    contract, plan
):
    normalized = contract.template_plan(plan)
    config = {
        "name": plan["name"],
        "description": normalized["description"],
        "template": 0,
        "cores": 1,
        "sockets": 1,
        "memory": "1024",
        "net0": "virtio=00:01:02:03:04:05,bridge=r42smk",
        "ipconfig0": "ip=10.42.70.30/24,gw=10.42.70.1",
        "scsi0": "local-lvm:vm-62000-disk-0,size=16G",
        "ide2": "local-lvm:vm-62000-cloudinit,media=cdrom",
        "cicustom": "vendor=local:snippets/" + normalized["snippet_name"],
    }
    assert contract.template_configured(config, normalized)
    for changes in (
        {"net1": "virtio,bridge=foreign"},
        {"ipconfig0": "ip=dhcp"},
        {"cores": 4},
        {"ide0": "foreign"},
        {"scsi0": "local-lvm:base-9901-disk-0,size=16G"},
        {"ciupgrade": 0},
        {"cicustom": "vendor=local:snippets/foreign.yaml"},
        {"scsi1": "foreign-disk"},
    ):
        with pytest.raises(ValueError):
            contract.template_configured({**config, **changes}, normalized)


def test_partial_resume_never_imports_over_unproven_or_shared_storage(contract, plan):
    normalized = contract.template_plan(plan)
    assert contract.template_disk_safe({}, normalized)
    assert contract.template_disk_safe(
        {"scsi0": "local-lvm:vm-62000-disk-0,size=8G"}, normalized
    )
    for config in (
        {"scsi0": "local-lvm:base-9901-disk-0,size=16G"},
        {"scsi0": "local-lvm:vm-62000-disk-0,size=32G"},
        {"unused0": "local-lvm:vm-62000-disk-0"},
        {"scsi1": "foreign"},
        {"ide1": "foreign"},
        {"ide2": "local:iso/foreign.iso,media=cdrom"},
        {"cicustom": "vendor=local:snippets/range42-apt-proxy.yaml"},
    ):
        with pytest.raises(ValueError):
            contract.template_disk_safe(config, normalized)


def test_partial_stopped_resume_requires_original_cpu_memory_and_bridge(contract, plan):
    normalized = contract.template_plan(plan)
    config = {
        "cores": "1",
        "sockets": "1",
        "memory": "1024",
        "net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=r42smk",
    }
    assert contract.template_partial_config(config, normalized)
    for changes in (
        {"cores": 4},
        {"memory": 2048},
        {"net0": "virtio,bridge=foreign"},
        {"ipconfig0": "ip=dhcp"},
    ):
        with pytest.raises(ValueError):
            contract.template_partial_config({**config, **changes}, normalized)


def test_cluster_identity_requires_exactly_one_valid_ca_fingerprint(contract):
    row = {"filename": "pve-root-ca.pem", "fingerprint": ":".join(["AA"] * 32)}
    assert (
        contract.template_cluster_identity([row]) == "pve-root-ca-sha256:" + "aa" * 32
    )
    for value in ([], {}, [row, row], [{**row, "fingerprint": "malformed"}]):
        with pytest.raises(ValueError):
            contract.template_cluster_identity(value)


def test_storage_preflight_refuses_unsupported_or_unknown_backends(contract, plan):
    normalized = contract.template_plan(plan)
    disk = {'type': 'lvmthin', 'active': 1, 'enabled': 1, 'content': 'images', 'avail': 20 * 1073741824}
    snippet = {'type': 'dir', 'active': 1, 'enabled': 1, 'content': 'snippets'}
    assert contract.template_storage(disk, snippet, normalized)
    for changes in ({'type': 'dir'}, {'type': 'unknown'}, {'avail': None}, {'avail': 1}, {'active': 0}):
        with pytest.raises(ValueError):
            contract.template_storage({**disk, **changes}, snippet, normalized)
