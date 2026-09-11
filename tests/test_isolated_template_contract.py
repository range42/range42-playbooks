"""Ownership and success proofs for an isolated Noble template build."""

import copy
import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

KEY_BLOB = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))
KEY = "ssh-ed25519 " + base64.b64encode(KEY_BLOB).decode() + " reviewed-builder"

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


def test_builder_key_requires_one_exact_reviewed_config_record(contract):
    from urllib.parse import quote

    expected = hashlib.sha256(KEY_BLOB).hexdigest()
    assert contract.template_key_sha256(KEY) == expected
    assert (
        contract.template_builder_key(
            {"ciuser": "alice", "sshkeys": quote(KEY, safe="")}, KEY, "alice"
        )
        == expected
    )
    for config in (
        {"ciuser": "alice"},
        {"ciuser": "bob", "sshkeys": KEY},
        {"ciuser": "alice", "sshkeys": KEY + "\n" + KEY},
        {"ciuser": "alice", "sshkeys": KEY.replace("reviewed-builder", "changed")},
        {"ciuser": "alice", "sshkeys": quote(quote(KEY, safe=""), safe="")},
    ):
        with pytest.raises(ValueError):
            contract.template_builder_key(config, KEY, "alice")


@pytest.mark.parametrize("user", ["alice; true", "alice --unexpected", "", None])
def test_builder_key_binding_requires_a_literal_guest_user(contract, user):
    with pytest.raises(ValueError):
        contract.template_builder_key({"ciuser": user, "sshkeys": KEY}, KEY, user)


def test_key_provisioning_preserves_existing_keys_and_only_allows_unconfigured_absence(
    contract,
):
    assert contract.template_key_provisionable({}, KEY, "alice")
    assert contract.template_key_provisionable(
        {"ciuser": "alice", "sshkeys": KEY}, KEY, "alice"
    )
    for config in (
        {"ciuser": "alice"},
        {"ipconfig0": "ip=10.42.70.30/24"},
        {"cicustom": "vendor=local:snippets/owned.yaml"},
        {"nameserver": "1.1.1.1"},
        {"ciuser": "alice", "sshkeys": "unknown-key"},
        {"ciuser": "alice", "sshkeys": KEY + "\n" + KEY},
    ):
        with pytest.raises(ValueError):
            contract.template_key_provisionable(config, KEY, "alice")


@pytest.mark.parametrize(
    "key",
    [
        "ssh-ed25519 AAAATEST",
        "ssh-ed25519 %%%",
        KEY + "\n" + KEY,
        'command="x" ' + KEY,
        "",
        None,
    ],
)
def test_builder_key_rejects_unreadable_multiple_or_option_bearing_records(
    contract, key
):
    with pytest.raises(ValueError):
        contract.template_key_sha256(key)


def test_final_cloudinit_seed_has_no_builder_or_unreviewed_authorization(contract):
    clean = "#cloud-config\nuser: alice\nssh_authorized_keys: []\n"
    assert contract.template_seed_clean({"ciuser": "alice"}, clean, KEY)
    for config, seed in (
        ({"sshkeys": KEY}, clean),
        ({}, "ssh_authorized_keys:\n  - " + KEY + "\n"),
        ({}, "users:\n  - name: alice\n    ssh_authorized_keys: [unknown-key]\n"),
        ({}, "ssh_import_id: [gh:unknown]\n"),
        ({}, "message: " + KEY + "\n"),
        ({}, "[]\n"),
    ):
        with pytest.raises(ValueError):
            contract.template_seed_clean(config, seed, KEY)


@pytest.mark.parametrize(
    "seed",
    [
        "ssh_authorized_keys: [" + KEY + "]\nssh_authorized_keys: []\n",
        "'" + KEY + "': ignored\n",
    ],
)
def test_seed_cannot_hide_authorization_in_duplicate_or_mapping_keys(contract, seed):
    with pytest.raises(ValueError):
        contract.template_seed_clean({}, seed, KEY)


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
        "cloud_init_warning_category": "none",
        "cloud_init_warning_count": 0,
    }
    assert contract.template_success(proof, normalized)
    for changes in (
        {"build_id": "c" * 32},
        {"plan_sha256": "c" * 64},
        {"cloud_init": "degraded done"},
        {"package_audit": "unavailable"},
        {"package_module": "missing"},
        {"cloud_init_warning_category": "unknown"},
        {"cloud_init_warning_count": True},
        {"cloud_init_warning_count": 2},
    ):
        with pytest.raises(ValueError):
            contract.template_success({**proof, **changes}, normalized)
    assert contract.template_success(
        {
            **proof,
            "cloud_init_warning_category": "proxmox_scalar_user_deprecation",
            "cloud_init_warning_count": 2,
        },
        normalized,
    )
    for count in (0, -1, 33, True, "2"):
        with pytest.raises(ValueError):
            contract.template_success(
                {
                    **proof,
                    "cloud_init_warning_category": "proxmox_scalar_user_deprecation",
                    "cloud_init_warning_count": count,
                },
                normalized,
            )


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
    disk = {
        "type": "lvmthin",
        "active": 1,
        "enabled": 1,
        "content": "images",
        "avail": 20 * 1073741824,
    }
    snippet = {"type": "dir", "active": 1, "enabled": 1, "content": "snippets"}
    assert contract.template_storage(disk, snippet, normalized)
    for changes in (
        {"type": "dir"},
        {"type": "unknown"},
        {"avail": None},
        {"avail": 1},
        {"active": 0},
    ):
        with pytest.raises(ValueError):
            contract.template_storage({**disk, **changes}, snippet, normalized)


def test_storage_preflight_accepts_native_zfs_volume_backend(contract, plan):
    normalized = contract.template_plan(plan)
    disk = {
        "type": "zfspool",
        "active": 1,
        "enabled": 1,
        "content": "rootdir,images",
        "avail": 20 * 1073741824,
    }
    snippet = {"type": "dir", "active": 1, "enabled": 1, "content": "iso,snippets"}
    assert contract.template_storage(disk, snippet, normalized)


def test_storage_volume_inventory_refuses_orphaned_or_ambiguous_disks(contract, plan):
    normalized = contract.template_plan(plan)
    assert contract.template_volumes([], {}, normalized)
    disk = {"volid": "local-lvm:vm-62000-disk-0", "vmid": 62000}
    attached = {"scsi0": disk["volid"] + ",size=16G"}
    assert contract.template_volumes([disk], attached, normalized)
    for rows, config in (
        ([disk], {}),
        ([], attached),
        ([disk, disk], attached),
        ({}, {}),
        ([{**disk, "vmid": 62001}], attached),
    ):
        with pytest.raises(ValueError):
            contract.template_volumes(rows, config, normalized)
