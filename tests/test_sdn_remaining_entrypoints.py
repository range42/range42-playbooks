"""Remaining SDN entrypoints must enter the same verified cluster flow."""

import importlib

import pytest

from test_sdn_cluster_composites import CONTROLLER, TARGET, run_composite


@pytest.mark.parametrize("fault", ["old", "incomplete", "foreign"])
def test_single_vnet_bootstrap_refuses_before_any_declaration_or_rule_write(
    tmp_path, fault
):
    result, observed = run_composite(
        tmp_path, "bootstrap.sdn_vnet", absent=fault != "foreign", **{fault: True}
    )
    assert result.returncode != 0
    assert all(
        action
        in [
            "network_list_sdn_zones",
            "network_list_sdn_vnets",
            "network_list_sdn_subnets",
            "network_snapshot_snat_rules",
        ]
        for action in observed["actions"]
    )


@pytest.mark.parametrize("count,applies", [(1, 0), (0, 1)])
def test_single_vnet_bootstrap_covers_members_and_applies_only_when_needed(
    tmp_path, count, applies
):
    result, observed = run_composite(tmp_path, "bootstrap.sdn_vnet", second_count=count)
    assert result.returncode == 0, result.stdout[-4500:] + result.stderr
    assert observed["intent"] == [
        {"source": TARGET, "vnet": "target", "zone": "lab", "want": 1}
    ]
    assert observed["actions"].count("network_apply_sdn") == applies
    assert "network_reconcile_snat_sources" in observed["actions"]
    assert "network_delete_extra_snat_rules" not in observed["actions"]


def test_single_vnet_bootstrap_passes_validated_new_zone_membership_to_actual_post(
    tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(CONTROLLER / "tests"))
    fixture = importlib.import_module("test_sdn_zone_nodes")
    with fixture.zone_api(tmp_path) as (host, ca, calls):
        result, observed = run_composite(
            tmp_path,
            "bootstrap.sdn_vnet",
            absent=True,
            membership=["pve2"],
            real_zone_api=(host, ca),
        )
    assert result.returncode == 0, result.stdout[-4500:] + result.stderr
    assert observed["new_zones"] == {"lab": ["pve2"]}
    assert calls == [{"zone": "lab", "type": "simple", "nodes": "pve2"}]
    assert [node["targets"] for node in observed["reconciled"]] == [
        [],
        [{"source": TARGET, "want": 1}],
    ]


@pytest.mark.parametrize("bundle", ["bootstrap", "bootstrap.sdn_vnet"])
def test_omitted_gateway_preserves_existing_gateway_without_apply(tmp_path, bundle):
    result, observed = run_composite(tmp_path, bundle, omit_gateway=True)
    assert result.returncode == 0, result.stdout[-4500:] + result.stderr
    assert "network_update_sdn_subnet" not in observed["actions"]
    assert "network_apply_sdn" not in observed["actions"]


def test_single_vnet_bootstrap_rejects_invalid_snat_before_writes(tmp_path):
    result, observed = run_composite(
        tmp_path,
        "bootstrap.sdn_vnet",
        absent=True,
        extra_vars={"BUNDLE_SDN_SUBNET_SNAT": 2},
    )
    assert result.returncode != 0
    assert observed["actions"] == []


def test_single_vnet_explicit_off_maps_to_disabled_declaration_and_intent(tmp_path):
    result, observed = run_composite(
        tmp_path, "bootstrap.sdn_vnet", extra_vars={"BUNDLE_SDN_SUBNET_SNAT": 0}
    )
    assert result.returncode == 0, result.stdout[-4500:] + result.stderr
    assert observed["intent"] == [
        {"source": TARGET, "vnet": "target", "zone": "lab", "want": 0}
    ]
    assert observed["actions"].count("network_update_sdn_subnet") == 1
    assert observed["actions"].count("network_apply_sdn") == 1
