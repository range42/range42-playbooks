"""Paired composites/controller with actual helpers and disposable per-node rules."""

import importlib
import json
import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = Path(
    os.environ.get(
        "RANGE42_CONTROLLER_TEST_ROOT",
        ROOT.parent / "range42-ansible_roles-proxmox_controller",
    )
)


@pytest.mark.parametrize(
    "initial", [0, 1], ids=["stable-no-apply", "verified-cluster-apply"]
)
def test_internet_off_preserves_nonmember_and_unrelated_rule_order(
    tmp_path, initial, monkeypatch
):
    # The paired checkout owns the real transport fixture. Keep controller task
    # loops, helpers, snapshot proofs, node workers and readbacks intact.
    monkeypatch.syspath_prepend(str(CONTROLLER / "tests"))
    fixture = importlib.import_module("test_snat_cluster_ansible")
    bundle = ROOT / "bundles/proxmox/sdn_network.internet_off/main.yml"
    tasks = yaml.safe_load(bundle.read_text())[0]["tasks"]
    for task in tasks:
        if "ansible.builtin.include_tasks" in task:
            task["ansible.builtin.include_tasks"] = str(
                (bundle.parent / task["ansible.builtin.include_tasks"]).resolve()
            )
    tasks.insert(
        0, {"ansible.builtin.set_fact": {"BUNDLE_SDN_SUBNET_ID": "lab-10.80.1.0-24"}}
    )
    io_tasks = [
        {
            "ansible.builtin.set_fact": {
                "network_list_sdn_subnets": [
                    {
                        "subnet": "lab-10.80.1.0-24",
                        "subnet_cidr": fixture.TARGET,
                        "subnet_vnet": "net1",
                        "subnet_snat": initial,
                    }
                ]
            },
            "when": "proxmox_vm_action == 'network_list_sdn_subnets'",
        },
        {
            "ansible.builtin.set_fact": {
                "network_list_sdn_vnets": [{"vnet": "net1", "vnet_zone": "lab"}]
            },
            "when": "proxmox_vm_action == 'network_list_sdn_vnets'",
        },
    ]
    result, observed = fixture.run_cluster(
        tmp_path, caller_tasks=tasks, fixture_role_tasks=io_tasks
    )
    assert result.returncode == 0, result.stdout[-6500:] + result.stderr
    assert Path(observed["apply_marker"]).exists() == bool(initial)
    assert json.loads(Path(observed["nodes"]["pve1"]["state"]).read_text()) == [
        fixture.UNRELATED,
        fixture.OTHER_RULE,
    ]
    assert json.loads(Path(observed["nodes"]["pve2"]["state"]).read_text()) == [
        fixture.UNRELATED,
        fixture.OTHER_RULE,
        fixture.TARGET_RULE,
    ]
    assert json.loads((tmp_path / "observed.json").read_text()) == {
        "snapshot_verified": True,
        "apply_attempted": bool(initial),
        "apply_verified": bool(initial),
    }


@pytest.mark.parametrize(
    "membership,expected_nodes", [(["pve2"], "pve2"), ("pve2", "pve2"), ([], None)]
)
def test_bootstrap_zone_post_matches_the_snapshot_membership(
    tmp_path, membership, expected_nodes, monkeypatch
):
    monkeypatch.syspath_prepend(str(CONTROLLER / "tests"))
    zone_fixture = importlib.import_module("test_sdn_zone_nodes")
    from test_sdn_cluster_composites import TARGET, run_composite

    with zone_fixture.zone_api(tmp_path) as (host, ca, calls):
        result, observed = run_composite(
            tmp_path,
            "bootstrap",
            absent=True,
            membership=membership,
            real_zone_api=(host, ca),
        )
    assert result.returncode == 0, result.stdout[-4500:] + result.stderr
    assert calls == [
        {
            "zone": "lab",
            "type": "simple",
            **({"nodes": expected_nodes} if expected_nodes else {}),
        }
    ]
    applicable = [
        node["node"]
        for node in observed["reconciled"]
        if {"source": TARGET, "want": 1} in node["targets"]
    ]
    assert applicable == (["pve2"] if expected_nodes else ["pve1", "pve2"])


def test_bootstrap_refuses_zone_post_when_fresh_quorum_evidence_disappears(
    tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(CONTROLLER / "tests"))
    zone_fixture = importlib.import_module("test_sdn_zone_nodes")
    from test_sdn_cluster_composites import run_composite

    status = [{"type": "node", "name": node, "online": 1} for node in ["pve1", "pve2"]]
    with zone_fixture.zone_api(tmp_path, status=status) as (host, ca, calls):
        result, _ = run_composite(
            tmp_path,
            "bootstrap",
            absent=True,
            membership=["pve2"],
            real_zone_api=(host, ca),
        )
    assert result.returncode != 0
    assert calls == []
