"""Real composite tasks and controller planner, with private role I/O fixtures."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = Path(
    os.environ.get(
        "RANGE42_CONTROLLER_TEST_ROOT",
        ROOT.parent / "range42-ansible_roles-proxmox_controller",
    )
)
TARGET = "10.80.1.0/24"


def run_composite(
    tmp_path,
    bundle,
    *,
    old=False,
    stale=False,
    incomplete=False,
    second_count=1,
    membership="pve1,pve2",
    absent=False,
    foreign=False,
    missing_zone=False,
    real_zone_api=None,
):
    role = tmp_path / "roles/range42-ansible_roles-proxmox_controller"
    (role / "tasks").mkdir(parents=True)
    (role / "files").mkdir()
    (role / "files/snat_cluster.py").write_bytes(
        (
            CONTROLLER
            / "roles/range42-ansible_roles-proxmox_controller/files/snat_cluster.py"
        ).read_bytes()
    )
    config = tmp_path / "config/secrets"
    config.mkdir(parents=True)
    (config / "default_vault.yml").write_text("proxmox_node: pve1\n")
    output = tmp_path / "observed.json"
    tasks = """
- ansible.builtin.set_fact:
    observed_actions: "{{ observed_actions | default([]) + [proxmox_vm_action] }}"
- ansible.builtin.set_fact:
    network_list_sdn_zones: "{{ fixture_zones }}"
  when: proxmox_vm_action == 'network_list_sdn_zones'
- ansible.builtin.set_fact:
    network_list_sdn_vnets: "{{ fixture_vnets }}"
  when: proxmox_vm_action == 'network_list_sdn_vnets'
- ansible.builtin.set_fact:
    network_list_sdn_subnets: "{{ fixture_subnets }}"
  when: proxmox_vm_action == 'network_list_sdn_subnets'
- ansible.builtin.set_fact:
    observed_intent: "{{ sdn_snat_desired_sources | default([]) }}"
    observed_new_zones: "{{ sdn_snat_new_zones | default({}) }}"
    network_snat_snapshot:
      version: 1
      node: pve1
      nat_counts: "{{ fixture_counts.pve1 }}"
      reviewed_policy:
        excluded_sources: "{{ sdn_snat_excluded_sources | default([]) }}"
        allow_new_rules: "{{ sdn_snat_allow_new_rules | default(false) }}"
  when: proxmox_vm_action == 'network_snapshot_snat_rules'
- block:
    - ansible.builtin.set_fact:
        network_snat_plan_input:
          desired_sources: "{{ sdn_snat_desired_sources | default([]) }}"
          new_zones: "{{ sdn_snat_new_zones | default({}) }}"
    - ansible.builtin.command:
        argv: ["{{ ansible_python_interpreter }}", -c, "{{ lookup('file', role_path ~ '/files/snat_cluster.py') }}", plan]
        stdin: "{{ {'primary_node':'pve1', 'status':[{'type':'node','name':'pve1','online':1},{'type':'node','name':'pve2','online':1}], 'cli_hosts':['ssh1','ssh2'], 'node_hosts':{'pve1':'ssh1','pve2':'ssh2'}, 'zones':fixture_zones, 'desired_sources':network_snat_plan_input.desired_sources, 'new_zones':network_snat_plan_input.new_zones, 'known_subnets':fixture_subnets, 'policy':network_snat_snapshot.reviewed_policy} | to_json }}"
      register: planned
      changed_when: false
    - ansible.builtin.set_fact:
        network_snat_plan: "{{ planned.stdout | from_json }}"
        network_snat_snapshot_verified: true
        network_snat_apply_attempted: false
        network_snat_apply_verified: false
        network_snat_snapshots: {}
        network_snat_reload_baseline: {}
    - ansible.builtin.set_fact:
        network_snat_snapshots: "{{ network_snat_snapshots | combine({item.node:{'version':1,'node':item.node,'nat_counts':fixture_counts[item.node],'reviewed_policy':item.policy,'captured_at':1234567890,'rules':[]}}) }}"
        network_snat_reload_baseline: "{{ network_snat_reload_baseline | combine({item.node:{'upids':[]}}) }}"
      loop: "{{ network_snat_plan.nodes }}"
      when: not (fixture_incomplete and item.node == 'pve2')
  when: proxmox_vm_action == 'network_snapshot_snat_rules' and not fixture_old
- ansible.builtin.set_fact:
    observed_reconciled: "{{ network_snat_plan.nodes | default([]) }}"
  when: proxmox_vm_action == 'network_reconcile_snat_sources'
- ansible.builtin.copy:
    dest: "{{ fixture_output }}"
    content: "{{ {'actions':observed_actions,'intent':observed_intent | default([]),'new_zones':observed_new_zones | default({}),'reconciled':observed_reconciled | default([])} | to_json }}"
"""
    if real_zone_api:
        (role / "tasks/add-zone.yml").write_bytes(
            (
                CONTROLLER
                / "roles/range42-ansible_roles-proxmox_controller/tasks/include/network/add_network_sdn_zone.yaml"
            ).read_bytes()
        )
        tasks += """
- ansible.builtin.include_tasks: add-zone.yml
  when: proxmox_vm_action == 'network_add_sdn_zone'
"""
    (role / "tasks/main.yml").write_text(tasks)
    vnet = {
        "vnet": "target",
        **({} if missing_zone else {"vnet_zone": "foreign" if foreign else "lab"}),
    }
    variables = {
        "BUNDLE_SDN_ZONE": "lab",
        "BUNDLE_SDN_SUBNET_ID": "lab-10.80.1.0-24",
        "BUNDLE_SDN_VNETS": [
            {"vnet": "target", "subnet": TARGET, "gateway": "10.80.1.1", "snat": True}
        ],
        "sdn_zone_nodes": membership,
        "fixture_zones": []
        if absent
        else [{"zone": "lab", "type": "simple", "nodes": membership}],
        "fixture_vnets": [] if absent else [vnet],
        "fixture_subnets": []
        if absent
        else [
            {
                "subnet": "lab-10.80.1.0-24",
                "subnet_cidr": TARGET,
                "subnet_vnet": "target",
                "subnet_snat": 1,
                "subnet_gateway": "10.80.1.1",
            }
        ],
        "fixture_counts": {"pve1": {TARGET: 1}, "pve2": {TARGET: second_count}},
        "fixture_old": old,
        "fixture_incomplete": incomplete,
        "fixture_output": str(output),
    }
    if real_zone_api:
        variables.update(
            proxmox_api_host=real_zone_api[0],
            proxmox_api_user="fixture",
            proxmox_api_token_id="fixture",
            proxmox_api_token_secret="fixture",
            proxmox_api_validate_certs=True,
        )
    if stale:
        variables.update(
            network_snat_plan={
                "version": 1,
                "primary_node": "pve1",
                "nodes": [{"node": "pve1", "host": "ssh1", "targets": []}],
            },
            network_snat_snapshots={"pve1": {"nat_counts": {TARGET: 1}}},
            network_snat_reload_baseline={"pve1": {"upids": []}},
            network_snat_plan_input={"desired_sources": [], "new_zones": {}},
        )
    inventory = tmp_path / "hosts.yml"
    inventory.write_text(
        yaml.safe_dump(
            {
                "all": {
                    "vars": {
                        "ansible_connection": "local",
                        "ansible_python_interpreter": sys.executable,
                    },
                    "children": {
                        "proxmox": {"hosts": {"api": {}}},
                        "proxmox_cli": {"hosts": {"ssh1": {}, "ssh2": {}}},
                    },
                }
            }
        )
    )
    wrapper = tmp_path / "run.yml"
    wrapper.write_text(
        yaml.safe_dump(
            [
                {
                    "import_playbook": str(
                        ROOT / f"bundles/proxmox/sdn_network.{bundle}/main.yml"
                    ),
                    "vars": variables,
                }
            ]
        )
    )
    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("ansible-playbook")),
            "-i",
            str(inventory),
            str(wrapper),
        ],
        env={
            **os.environ,
            "ANSIBLE_ROLES_PATH": str(tmp_path / "roles"),
            "RANGE42_ACTIVE_CONFIG_DIR": str(config.parent),
            "ANSIBLE_NOCOLOR": "1",
            **({"SSL_CERT_FILE": str(real_zone_api[1])} if real_zone_api else {}),
        },
        text=True,
        capture_output=True,
        timeout=60,
    )
    return result, json.loads(output.read_text()) if output.exists() else {
        "actions": []
    }


@pytest.mark.parametrize("bundle", ["bootstrap", "internet_on"])
def test_missing_enabled_rule_on_second_zone_member_requires_apply(tmp_path, bundle):
    result, observed = run_composite(tmp_path, bundle, second_count=0)
    assert result.returncode == 0, result.stdout[-4500:] + result.stderr
    assert observed["intent"] == [
        {"source": TARGET, "vnet": "target", "zone": "lab", "want": 1}
    ]
    assert observed["actions"].count("network_apply_sdn") == 1
    assert "network_reconcile_snat_sources" in observed["actions"]
    assert "network_delete_extra_snat_rules" not in observed["actions"]


def test_nonmember_missing_rule_does_not_trigger_global_apply(tmp_path):
    result, observed = run_composite(
        tmp_path, "internet_on", second_count=0, membership="pve1"
    )
    assert result.returncode == 0, result.stdout[-4500:] + result.stderr
    assert "network_apply_sdn" not in observed["actions"]
    assert [node["targets"] for node in observed["reconciled"]] == [
        [{"source": TARGET, "want": 1}],
        [],
    ]


def test_new_zone_snapshot_uses_the_same_membership_as_zone_creation(tmp_path):
    result, observed = run_composite(
        tmp_path, "bootstrap", absent=True, membership="pve2", second_count=0
    )
    assert result.returncode == 0, result.stdout[-4500:] + result.stderr
    assert observed["new_zones"] == {"lab": "pve2"}
    assert [node["targets"] for node in observed["reconciled"]] == [
        [],
        [{"source": TARGET, "want": 1}],
    ]


@pytest.mark.parametrize("bundle", ["bootstrap", "internet_on", "apply"])
@pytest.mark.parametrize("fault", ["old", "incomplete"])
def test_missing_current_cluster_coverage_refuses_before_any_write(
    tmp_path, bundle, fault
):
    result, observed = run_composite(tmp_path, bundle, stale=True, **{fault: True})
    assert result.returncode != 0, (
        "An old/partial controller snapshot must not authorize a write"
    )
    assert all(
        action
        in (
            "network_list_sdn_zones",
            "network_list_sdn_vnets",
            "network_list_sdn_subnets",
            "network_snapshot_snat_rules",
        )
        for action in observed["actions"]
    )


@pytest.mark.parametrize(
    "bundle,fault", [("bootstrap", "foreign"), ("internet_on", "missing_zone")]
)
def test_vnet_zone_binding_must_be_authoritative_before_mutation(
    tmp_path, bundle, fault
):
    result, observed = run_composite(tmp_path, bundle, **{fault: True})
    assert result.returncode != 0, (
        "Unverifiable or conflicting VNet ownership must stop the composite"
    )
    assert "network_snapshot_snat_rules" not in observed["actions"]
