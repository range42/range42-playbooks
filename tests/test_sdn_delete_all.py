"""Actual deletion APIs and cluster preservation tasks use retained before-state."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = Path(os.environ["RANGE42_CONTROLLER_TEST_ROOT"])


def paired(tmp_path, monkeypatch, *, fault=None, **options):
    monkeypatch.syspath_prepend(str(CONTROLLER / "tests"))
    spec = importlib.util.spec_from_file_location(
        "delete_cluster_fixture", CONTROLLER / "tests/test_snat_cluster_ansible.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    from test_sdn_delete_scope import document

    source = document()
    source["families"]["vnets"][0]["vnet"] = "net1"
    source["subnets"]["net1"] = source["subnets"].pop("target")
    if fault == "missing_cidr":
        source["subnets"]["net1"][0].pop("cidr")
    if fault == "pending":
        source["families"]["controllers"] = [
            {"controller": "other", "state": "changed"}
        ]
    if fault == "attached":
        source["guest_configs"]["qemu/100"]["current"]["net0"] = "bridge=net1"
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps(source))
    after = json.loads(json.dumps(source))
    after["families"]["zones"].pop(0)
    after["families"]["vnets"].pop(0)
    after["subnets"].pop("net1")
    (tmp_path / "after.json").write_text(json.dumps(after))
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("RANGE42_ACTIVE_CONFIG_DIR", str(config))
    monkeypatch.setenv("RANGE42_SDN_DELETE_STATE_DIR", str(config))
    tasks = yaml.safe_load(
        (ROOT / "bundles/proxmox/sdn_network.delete.all/main.yml").read_text()
    )[0]["tasks"]

    def resolve_includes(value):
        if isinstance(value, list):
            return [resolve_includes(item) for item in value]
        if not isinstance(value, dict):
            return value
        for key in ("ansible.builtin.include_tasks", "include_tasks"):
            if key in value:
                value[key] = str(
                    (
                        ROOT / "bundles/proxmox/sdn_network.delete.all" / value[key]
                    ).resolve()
                )
        return {key: resolve_includes(item) for key, item in value.items()}

    tasks = resolve_includes(tasks)
    tasks.insert(0, {"ansible.builtin.set_fact": {"BUNDLE_SDN_ZONE": "lab"}})
    io = [
        {
            "ansible.builtin.command": {
                "argv": [
                    sys.executable,
                    "-c",
                    "{{ lookup('file', role_path ~ '/files/snat_cluster.py') }}",
                    "delete-scope",
                ],
                "stdin": "{{ lookup('file', '"
                + str(scope_path)
                + "' if not (network_snat_apply_verified | default(false)) else '"
                + str(tmp_path / "after.json")
                + "') }}",
            },
            "register": "fixture_delete_scope",
            "when": "proxmox_vm_action == 'network_plan_sdn_delete'",
            "changed_when": False,
        },
        {
            "ansible.builtin.set_fact": {
                "network_plan_sdn_delete": {
                    "scope": "{{ (fixture_delete_scope.stdout | from_json) | combine({'cluster_identity':'pve-root-ca-sha256:' ~ ('ab' * 32)}) }}",
                    "node": "pve1",
                    "privileged": True,
                }
            },
            "when": "proxmox_vm_action == 'network_plan_sdn_delete'",
        },
        {
            "ansible.builtin.include_tasks": "include/network/sdn_delete_journal.yaml",
            "when": "proxmox_vm_action == 'network_sdn_delete_journal'",
        },
    ]
    if fault == "drift":
        io.insert(
            0,
            {
                "ansible.builtin.set_fact": {
                    "fixture_scope_reads": "{{ (fixture_scope_reads | default(0) | int) + 1 }}"
                },
                "when": "proxmox_vm_action == 'network_plan_sdn_delete'",
            },
        )
        io.append(
            {
                "ansible.builtin.set_fact": {
                    "network_plan_sdn_delete": "{{ network_plan_sdn_delete | combine({'scope': network_plan_sdn_delete.scope | combine({'zone_nodes':['pve2']})}) }}"
                },
                "when": "proxmox_vm_action == 'network_plan_sdn_delete' and (fixture_scope_reads | int) == 2",
            }
        )
    result, observed = fixture.run_cluster(
        tmp_path,
        caller_tasks=tasks,
        fixture_role_tasks=io,
        target_counts={"pve1": 3, "pve2": 2},
        deletion_fixture={
            "log": str(tmp_path / "deletions.json"),
            "fail_at": 2 if fault == "partial" else None,
        },
        **options,
    )
    return result, observed, fixture


def test_delete_removes_zone_then_cleans_members_and_preserves_every_other_rule(
    tmp_path, monkeypatch
):
    result, observed, fixture = paired(tmp_path, monkeypatch)
    assert result.returncode == 0, result.stdout[-8000:] + result.stderr
    assert json.loads((tmp_path / "deletions.json").read_text()) == [
        "/api2/json/cluster/sdn/vnets/net1/subnets/lab-10.42.70.0-24",
        "/api2/json/cluster/sdn/vnets/net1",
        "/api2/json/cluster/sdn/zones/lab",
    ]
    assert Path(observed["apply_marker"]).exists()
    assert json.loads(Path(observed["nodes"]["pve1"]["state"]).read_text()) == [
        fixture.UNRELATED,
        fixture.OTHER_RULE,
    ]
    assert (
        json.loads(Path(observed["nodes"]["pve2"]["state"]).read_text())
        == [fixture.UNRELATED, fixture.OTHER_RULE] + [fixture.TARGET_RULE] * 2
    )
    journal = json.loads((tmp_path / "config/.sdn-delete/lab.json").read_text())
    assert journal["state"] == "completed"
    assert journal["payload"]["scope"]["desired_sources"][0]["want"] == 0
    assert set(journal["payload"]["snapshots"]) == {"pve1", "pve2"}
    journal_path = tmp_path / "config/.sdn-delete/lab.json"
    before = journal_path.read_bytes()
    (tmp_path / "scope.json").write_bytes((tmp_path / "after.json").read_bytes())
    again = repeat(tmp_path)
    assert again.returncode == 0, again.stdout[-4000:] + again.stderr
    assert journal_path.read_bytes() == before
    assert len(json.loads((tmp_path / "deletions.json").read_text())) == 3


@pytest.mark.parametrize(
    "fault", ["missing_cidr", "pending", "attached", "offline", "wrong_host", "drift"]
)
def test_delete_refuses_unproven_scope_before_first_declaration(
    tmp_path, monkeypatch, fault
):
    options = {fault: True} if fault in ("offline", "wrong_host") else {}
    result, observed, _ = paired(tmp_path, monkeypatch, fault=fault, **options)
    assert result.returncode != 0
    assert not (tmp_path / "deletions.json").exists()
    assert not Path(observed["apply_marker"]).exists()


def test_partial_delete_retains_original_scope_and_refuses_cleanup(
    tmp_path, monkeypatch
):
    result, observed, _ = paired(tmp_path, monkeypatch, fault="partial")
    assert result.returncode != 0
    assert len(json.loads((tmp_path / "deletions.json").read_text())) == 1
    assert not Path(observed["apply_marker"]).exists()
    journal = json.loads((tmp_path / "config/.sdn-delete/lab.json").read_text())
    assert journal["state"] != "completed"
    assert journal["payload"]["scope"]["subnets"][0]["subnet_cidr"] == "10.42.70.0/24"
    journal_path = tmp_path / "config/.sdn-delete/lab.json"
    before = journal_path.read_bytes()
    (tmp_path / "scope.json").write_bytes((tmp_path / "after.json").read_bytes())
    again = repeat(tmp_path)
    assert again.returncode != 0
    assert journal_path.read_bytes() == before
    assert len(json.loads((tmp_path / "deletions.json").read_text())) == 1
    assert all(
        json.loads(Path(record["writes"]).read_text()) == []
        for record in observed["nodes"].values()
    )


def repeat(tmp_path):
    return subprocess.run(
        [
            str(Path(sys.executable).with_name("ansible-playbook")),
            "-i",
            str(tmp_path / "hosts.yml"),
            str(tmp_path / "playbook.yml"),
        ],
        env={
            **os.environ,
            "ANSIBLE_ROLES_PATH": str(tmp_path / "roles"),
            "ANSIBLE_LIBRARY": str(tmp_path / "library"),
            "ANSIBLE_NOCOLOR": "1",
        },
        capture_output=True,
        text=True,
        timeout=45,
    )


def test_failed_node_reload_retains_evidence_without_rule_cleanup(
    tmp_path, monkeypatch
):
    result, observed, _ = paired(tmp_path, monkeypatch, failed=True)
    assert result.returncode != 0
    assert len(json.loads((tmp_path / "deletions.json").read_text())) == 3
    assert Path(observed["apply_marker"]).exists()
    assert all(
        json.loads(Path(record["writes"]).read_text()) == []
        for record in observed["nodes"].values()
    )
    journal = json.loads((tmp_path / "config/.sdn-delete/lab.json").read_text())
    assert journal["state"] != "completed"
