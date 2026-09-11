"""Standalone NAT operations need an authoritative scope before any rule write."""

import importlib
import json
from pathlib import Path

import yaml

import pytest

from test_sdn_cluster_composites import CONTROLLER, ROOT, TARGET, run_composite

BUNDLE = "reconcile.snat_rules"
READS = {
    "network_list_sdn_subnets",
    "network_list_sdn_vnets",
    "network_snapshot_snat_rules",
    "network_count_snat_source",
}


@pytest.mark.parametrize("want", [-1, 2, 100, "0", True, None, 1.0])
def test_invalid_want_refuses_before_any_role_action(tmp_path, want):
    result, observed = run_composite(
        tmp_path, BUNDLE, extra_vars={"BUNDLE_SDN_SNAT_WANT": want}
    )
    assert result.returncode != 0
    assert observed["actions"] == []


@pytest.mark.parametrize(
    "fault", ["absent", "ambiguous", "foreign", "missing_zone", "mismatched_snat"]
)
def test_mutation_requires_unique_authoritative_matching_source(tmp_path, fault):
    variables = {"BUNDLE_SDN_SNAT_WANT": 0 if fault == "mismatched_snat" else 1}
    if fault == "ambiguous":
        variables["fixture_subnets"] = [
            {
                "subnet": "one",
                "subnet_cidr": TARGET,
                "subnet_vnet": "target",
                "subnet_snat": 1,
            },
            {
                "subnet": "two",
                "subnet_cidr": TARGET,
                "subnet_vnet": "other",
                "subnet_snat": 1,
            },
        ]
    result, observed = run_composite(
        tmp_path,
        BUNDLE,
        extra_vars=variables,
        **({fault: True} if fault in ["absent", "foreign", "missing_zone"] else {}),
    )
    assert result.returncode != 0
    assert set(observed["actions"]) <= READS


@pytest.mark.parametrize("fault", ["old", "incomplete"])
@pytest.mark.parametrize("want", [1, 99])
def test_stale_or_incomplete_coverage_cannot_authorize_mutation(tmp_path, fault, want):
    result, observed = run_composite(
        tmp_path,
        BUNDLE,
        stale=True,
        extra_vars={"BUNDLE_SDN_SNAT_WANT": want},
        **{fault: True},
    )
    assert result.returncode != 0
    assert set(observed["actions"]) <= READS


def test_mutation_uses_exact_source_intent_without_apply_or_declaration_write(tmp_path):
    result, observed = run_composite(tmp_path, BUNDLE, membership="pve2")
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr
    assert observed["intent"] == [
        {"source": TARGET, "vnet": "target", "zone": "lab", "want": 1}
    ]
    assert set(observed["actions"]) <= READS | {"network_reconcile_snat_sources"}
    assert [node["targets"] for node in observed["reconciled"]] == [
        [],
        [{"source": TARGET, "want": 1}],
    ]


def paired(
    tmp_path, monkeypatch, *, want, initial, absent=False, counts=None, **options
):
    monkeypatch.syspath_prepend(str(CONTROLLER / "tests"))
    fixture = importlib.import_module("test_snat_cluster_ansible")
    bundle = ROOT / "bundles/proxmox/sdn_network.reconcile.snat_rules/main.yml"
    tasks = yaml.safe_load(bundle.read_text())[0]["tasks"]
    for task in tasks:
        if "ansible.builtin.include_tasks" in task:
            task["ansible.builtin.include_tasks"] = str(
                (bundle.parent / task["ansible.builtin.include_tasks"]).resolve()
            )
    tasks.insert(
        0,
        {
            "ansible.builtin.set_fact": {
                "BUNDLE_SDN_SUBNET_CIDR": fixture.TARGET,
                "BUNDLE_SDN_SNAT_WANT": want,
                "network_count_snat_source": {"stale": True},
            }
        },
    )
    tasks.append(
        {
            "ansible.builtin.copy": {
                "dest": str(tmp_path / "count.json"),
                "content": "{{ {'counts': network_count_snat_source | default(none), 'legacy': network_delete_extra_snat_rules | default(none)} | to_json }}",
            }
        }
    )
    io = [
        {
            "ansible.builtin.set_fact": {
                "network_list_sdn_subnets": []
                if absent
                else [
                    {
                        "subnet": "lab-test",
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
        tmp_path,
        caller_tasks=tasks,
        fixture_role_tasks=io,
        target_counts=counts,
        **options,
    )
    return result, observed, fixture


def test_99_counts_more_than_99_rules_after_deletion_without_any_mutation(
    tmp_path, monkeypatch
):
    counts = {"pve1": 105, "pve2": 3}
    result, observed, fixture = paired(
        tmp_path, monkeypatch, want=99, initial=0, absent=True, counts=counts
    )
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr
    assert not Path(observed["apply_marker"]).exists()
    for node, record in observed["nodes"].items():
        assert (
            json.loads(Path(record["state"]).read_text())
            == [fixture.UNRELATED, fixture.OTHER_RULE]
            + [fixture.TARGET_RULE] * counts[node]
        )
        assert json.loads(Path(record["writes"]).read_text()) == []
    output = json.loads((tmp_path / "count.json").read_text())
    assert output["counts"]["read_only"] is True
    assert {row["node"]: row["count"] for row in output["counts"]["nodes"]} == counts
    assert output["legacy"]["snat_before"] == 105
    assert output["legacy"]["read_only"] is True
    assert output["legacy"]["proxmox_node"] == "pve1"
    assert output["legacy"]["nodes"] == output["counts"]["nodes"]


@pytest.mark.parametrize("want", [0, 1])
def test_standalone_reconcile_preserves_external_and_nonmember_rules(
    tmp_path, monkeypatch, want
):
    result, observed, fixture = paired(
        tmp_path, monkeypatch, want=want, initial=want, counts={"pve1": 3, "pve2": 2}
    )
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr
    assert not Path(observed["apply_marker"]).exists()
    assert (
        json.loads(Path(observed["nodes"]["pve1"]["state"]).read_text())
        == [fixture.UNRELATED, fixture.OTHER_RULE] + [fixture.TARGET_RULE] * want
    )
    assert (
        json.loads(Path(observed["nodes"]["pve2"]["state"]).read_text())
        == [fixture.UNRELATED, fixture.OTHER_RULE] + [fixture.TARGET_RULE] * 2
    )


def test_standalone_refuses_missing_enabled_rule_without_creating_or_deleting(
    tmp_path, monkeypatch
):
    result, observed, _ = paired(
        tmp_path, monkeypatch, want=1, initial=1, counts={"pve1": 0, "pve2": 2}
    )
    assert result.returncode != 0
    assert not Path(observed["apply_marker"]).exists()
    assert all(
        json.loads(Path(record["writes"]).read_text()) == []
        for record in observed["nodes"].values()
    )


@pytest.mark.parametrize("fault", ["offline", "wrong_host"])
def test_read_only_counts_refuse_unverified_nodes(tmp_path, monkeypatch, fault):
    result, observed, _ = paired(
        tmp_path, monkeypatch, want=99, initial=0, absent=True, **{fault: True}
    )
    assert result.returncode != 0
    assert not Path(observed["apply_marker"]).exists()
    assert all(
        json.loads(Path(record["writes"]).read_text()) == []
        for record in observed["nodes"].values()
    )
