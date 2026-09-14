"""Real legacy CLI and Ansible consume concrete manifests before any SDN role."""

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios/blank_scenario_2_sdn"


def manifest():
    return {
        "scenario": "fixture",
        "version": 3,
        "vms": [
            {
                "vm_id": 60000,
                "vm_name": "fixture",
                "template_vm_id": 9901,
                "ip": "10.42.70.10",
                "bridge": "net1",
                "nics": [
                    {"index": 0, "bridge": "net1", "ip": "10.42.70.10", "prefix": 24},
                    {"index": 1, "bridge": "net2", "ip": "10.42.71.10", "prefix": 24},
                    {
                        "index": 2,
                        "bridge": "vmbr140",
                        "ip": "10.42.140.10",
                        "prefix": 24,
                    },
                ],
            }
        ],
        "templates": [{"vm_id": 9901}],
    }


def invoke(tmp_path, document):
    scenario = tmp_path / "scenario"
    shutil.copytree(SCENARIO / "00_sdn_bootstrap", scenario / "00_sdn_bootstrap")
    (scenario / "manifest").mkdir()
    (scenario / "manifest/scenario_vms.json").write_text(json.dumps(document))
    script = scenario / "scenario.delete_networks.sh"
    shutil.copyfile(SCENARIO / "blank_scenario_2_sdn.delete_networks.sh", script)
    bundle = tmp_path / "bundles/proxmox/sdn_network.delete.selected"
    bundle.mkdir(parents=True)
    receipt = tmp_path / "selected.json"
    # Only the transport boundary is replaced: the real CLI/adapter must fully
    # validate the manifest before it can reach the guarded bundle's contract.
    (bundle / "main.yml").write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "proxmox",
                    "gather_facts": False,
                    "tasks": [
                        {
                            "ansible.builtin.copy": {
                                "dest": str(receipt),
                                "content": "{{ {'vnets': BUNDLE_SDN_VNETS, 'zone': BUNDLE_SDN_ZONE, 'read_only': BUNDLE_SDN_DELETE_READ_ONLY} | to_json }}",
                            },
                        }
                    ],
                }
            ]
        )
    )
    (tmp_path / "inventory_default.yml").write_text(
        yaml.safe_dump(
            {
                "all": {
                    "children": {
                        "proxmox": {
                            "hosts": {
                                "localhost": {
                                    "ansible_connection": "local",
                                    "ansible_python_interpreter": sys.executable,
                                }
                            }
                        }
                    }
                },
            }
        )
    )
    password = tmp_path / "password"
    password.write_text("fixture-only\n")
    result = subprocess.run(
        ["bash", str(script), "--dry-run", "-e", '{"range42_sdn_zone":"lab"}'],
        env={
            **os.environ,
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
            "RANGE42_BUNDLE_DIR": str(tmp_path / "bundles"),
            "RANGE42_ANSIBLE_ROLES__INVENTORY_DIR": str(tmp_path),
            "RANGE42_VAULT_PASSWORD_FILE": str(password),
            "ANSIBLE_NOCOLOR": "1",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result, receipt


def test_cli_v3_selects_primary_and_all_additional_nics_without_templates_or_ip_inference(
    tmp_path,
):
    result, receipt = invoke(tmp_path, manifest())
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr
    assert json.loads(receipt.read_text()) == {
        "vnets": ["net1", "net2"],
        "zone": "lab",
        "read_only": True,
    }


@pytest.mark.parametrize(
    "fault",
    [
        "missing_nics",
        "null_nics",
        "empty_nics",
        "mapping_nics",
        "scalar_nic",
        "duplicate_index",
        "gap_index",
        "boolean_index",
        "missing_bridge",
        "wrong_bridge_type",
        "contradictory_bridge",
        "contradictory_ip",
        "template_nics",
        "unsupported_version",
        "legacy_nics",
    ],
)
def test_cli_rejects_ambiguous_nic_scope_before_entering_the_guarded_bundle(
    tmp_path, fault
):
    value = deepcopy(manifest())
    vm = value["vms"][0]
    if fault == "missing_nics":
        del vm["nics"]
    elif fault in {"null_nics", "empty_nics", "mapping_nics"}:
        vm["nics"] = {
            "null_nics": None,
            "empty_nics": [],
            "mapping_nics": {"net1": {}},
        }[fault]
    elif fault == "scalar_nic":
        vm["nics"][1] = "net2"
    elif fault in {"duplicate_index", "gap_index", "boolean_index"}:
        vm["nics"][1]["index"] = {
            "duplicate_index": 0,
            "gap_index": 4,
            "boolean_index": True,
        }[fault]
    elif fault == "missing_bridge":
        del vm["nics"][1]["bridge"]
    elif fault == "wrong_bridge_type":
        vm["nics"][1]["bridge"] = ["net2"]
    elif fault == "contradictory_bridge":
        vm["bridge"] = "net3"
    elif fault == "contradictory_ip":
        vm["ip"] = "10.42.70.11"
    elif fault == "template_nics":
        value["templates"][0]["nics"] = [{"index": 0, "bridge": "net3"}]
    elif fault == "unsupported_version":
        value["version"] = 4
    elif fault == "legacy_nics":
        value["version"] = 2
    result, receipt = invoke(tmp_path, value)
    assert result.returncode != 0, result.stdout[-3000:]
    assert not receipt.exists(), "Invalid manifest reached the SDN deletion bundle"


@pytest.mark.parametrize("version", [1, 2])
def test_cli_preserves_legacy_primary_and_template_bridges(tmp_path, version):
    result, receipt = invoke(
        tmp_path,
        {
            "version": version,
            "vms": [{"bridge": "net1"}, {"bridge": "vmbr140"}],
            "templates": [{"bridge": "net2"}, {"vm_id": 9901}],
        },
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr
    assert json.loads(receipt.read_text())["vnets"] == ["net1", "net2"]


@pytest.mark.parametrize("mode", ["delete", "preview", "foreign_nic"])
def test_actual_cli_scopes_all_nics_and_preserves_other_zones_and_nonmembers(
    tmp_path, monkeypatch, mode
):
    from test_sdn_delete_all import paired

    initial, observed, fixture = paired(
        tmp_path, monkeypatch, selected=True, read_only=True
    )
    assert initial.returncode == 0, initial.stdout[-6000:] + initial.stderr
    before = json.loads((tmp_path / "scope.json").read_text())
    after = json.loads((tmp_path / "after.json").read_text())
    # Preserve the fixture's unrelated, attached same-zone VNet. Also include a
    # separate zone with its own VNet/guest and NAT rule throughout deletion.
    for document in (before, after):
        document["families"]["vnets"].append(
            {
                "vnet": "net9",
                "zone": "external",
                "state": "unchanged",
            }
        )
        document["subnets"]["net9"] = [
            {
                "subnet": "external-10.42.90.0-24",
                "cidr": "10.42.90.0/24",
                "state": "unchanged",
            }
        ]
        document["guests"].append({"vmid": 101, "type": "qemu", "node": "pve1"})
        document["guest_configs"]["qemu/101"] = {
            "current": {"net0": "virtio,bridge=net9"},
            "pending": [{"key": "net0", "value": "virtio,bridge=net9"}],
        }
    before["families"]["vnets"].append(
        {
            "vnet": "net2",
            "zone": "lab",
            "state": "unchanged",
        }
    )
    before["subnets"]["net2"] = [
        {
            "subnet": "lab-10.42.71.0-24",
            "cidr": "10.42.71.0/24",
            "state": "unchanged",
        }
    ]
    (tmp_path / "scope.json").write_text(json.dumps(before))
    (tmp_path / "after.json").write_text(json.dumps(after))
    api_file = tmp_path / "api.json"
    api = json.loads(api_file.read_text())
    api["zones"].append({"zone": "external", "type": "simple"})
    api_file.write_text(json.dumps(api))
    secondary_rule = [
        part.replace("10.42.70.0/24", "10.42.71.0/24") for part in fixture.TARGET_RULE
    ]
    foreign_rule = [
        part.replace("10.42.70.0/24", "10.42.90.0/24") for part in fixture.TARGET_RULE
    ]
    baseline = {}
    for name, node in observed["nodes"].items():
        path = Path(node["state"])
        baseline[name] = json.loads(path.read_text()) + [secondary_rule, foreign_rule]
        path.write_text(json.dumps(baseline[name]))

    scenario = tmp_path / "cli-scenario"
    shutil.copytree(SCENARIO / "00_sdn_bootstrap", scenario / "00_sdn_bootstrap")
    (scenario / "manifest").mkdir()
    value = manifest()
    if mode == "foreign_nic":
        value["vms"][0]["nics"][1]["bridge"] = "net9"
    (scenario / "manifest/scenario_vms.json").write_text(json.dumps(value))
    script = scenario / "scenario.delete_networks.sh"
    shutil.copyfile(SCENARIO / "blank_scenario_2_sdn.delete_networks.sh", script)
    config = tmp_path / "config"
    (config / "secrets").mkdir()
    variables = yaml.safe_load((tmp_path / "playbook.yml").read_text())[0]["vars"]
    variables["range42_sdn_zone"] = "lab"
    (config / "secrets/default_vault.yml").write_text(yaml.safe_dump(variables))
    password = tmp_path / "password"
    password.write_text("fixture-only\n")
    shutil.copyfile(tmp_path / "hosts.yml", tmp_path / "inventory_default.yml")
    result = subprocess.run(
        ["bash", str(script), *(["--dry-run"] if mode == "preview" else [])],
        env={
            **os.environ,
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
            "RANGE42_BUNDLE_DIR": str(ROOT / "bundles"),
            "RANGE42_ANSIBLE_ROLES__INVENTORY_DIR": str(tmp_path),
            "RANGE42_VAULT_PASSWORD_FILE": str(password),
            "ANSIBLE_ROLES_PATH": str(tmp_path / "roles"),
            "ANSIBLE_LIBRARY": str(tmp_path / "library"),
            "ANSIBLE_NOCOLOR": "1",
        },
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert (result.returncode == 0) == (mode != "foreign_nic"), (
        result.stdout[-8000:] + result.stderr
    )
    assert json.loads(api_file.read_text())["zones"] == api["zones"]
    if mode != "delete":
        assert not (tmp_path / "deletions.json").exists()
        assert not Path(observed["apply_marker"]).exists()
        assert not (config / ".sdn-delete/lab.json").exists()
        for name, node in observed["nodes"].items():
            assert json.loads(Path(node["state"]).read_text()) == baseline[name]
            assert json.loads(Path(node["writes"]).read_text()) == []
        if mode == "preview":
            assert '"net1"' in result.stdout and '"net2"' in result.stdout
        return
    assert json.loads((tmp_path / "deletions.json").read_text()) == [
        "/api2/json/cluster/sdn/vnets/net1/subnets/lab-10.42.70.0-24",
        "/api2/json/cluster/sdn/vnets/net2/subnets/lab-10.42.71.0-24",
        "/api2/json/cluster/sdn/vnets/net1",
        "/api2/json/cluster/sdn/vnets/net2",
    ]
    for name, node in observed["nodes"].items():
        expected = (
            baseline[name]
            if name == "pve2"
            else [
                rule
                for rule in baseline[name]
                if rule not in (fixture.TARGET_RULE, secondary_rule)
            ]
        )
        assert json.loads(Path(node["state"]).read_text()) == expected
    journal = json.loads((config / ".sdn-delete/lab.json").read_text())
    assert journal["state"] == "completed"
    assert journal["payload"]["scope"]["requested_vnets"] == ["net1", "net2"]
    assert journal["payload"]["scope"]["selection"] == "vnets"
