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
