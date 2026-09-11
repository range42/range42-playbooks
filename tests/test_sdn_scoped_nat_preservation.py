"""Exercise real bundle orchestration while replacing only the PVE role boundary."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TARGET = "10.80.1.0/24"


def run_bundle(tmp_path, mode, initial):
    config = tmp_path / "config"
    (config / "secrets").mkdir(parents=True)
    (config / "secrets/default_vault.yml").write_text("proxmox_node: pve-test\n")
    role = tmp_path / "roles/range42-ansible_roles-proxmox_controller/tasks"
    role.mkdir(parents=True)
    (role / "main.yml").write_text("""- ansible.builtin.set_fact:
    observed_actions: "{{ observed_actions | default([]) + [proxmox_vm_action] }}"
- ansible.builtin.set_fact:
    network_list_sdn_subnets: "{{ fixture_subnets }}"
  when: proxmox_vm_action == 'network_list_sdn_subnets'
- ansible.builtin.set_fact:
    network_list_snat_rules: "{{ fixture_rules }}"
  when: proxmox_vm_action == 'network_list_snat_rules'
- ansible.builtin.set_fact:
    network_snat_snapshot:
      version: 1
      node: pve-test
      nat_counts: "{{ fixture_rules | items2dict(key_name='snat_source', value_name='snat_count') }}"
  when: proxmox_vm_action == 'network_snapshot_snat_rules'
- ansible.builtin.set_fact:
    observed_restoration: "{{ observed_restoration | default([]) + [sdn_snat_excluded_sources] }}"
  when: proxmox_vm_action == 'network_restore_snat_snapshot'
- ansible.builtin.set_fact:
    observed_reconciliation: "{{ observed_reconciliation | default([]) + [{'cidr': sdn_subnet_cidr, 'want': sdn_snat_want | int}] }}"
  loop: ['controller-inner-loop']
  when: proxmox_vm_action == 'network_delete_extra_snat_rules'
""")
    inventory = tmp_path / "hosts.ini"
    inventory.write_text(
        f"proxmox ansible_connection=local ansible_python_interpreter={sys.executable}\n"
    )
    output = tmp_path / "observed.json"
    wrapper = tmp_path / "scenario.yml"
    wrapper.write_text(f"""- import_playbook: {ROOT}/bundles/proxmox/sdn_network.internet_{mode}/main.yml
- hosts: proxmox
  gather_facts: false
  tasks:
    - ansible.builtin.copy:
        dest: {output}
        content: "{{{{ {{'actions': observed_actions, 'reconciled': observed_reconciliation}} | to_json }}}}"
""")
    fixture = {
        "BUNDLE_SDN_SUBNET_ID": "zone-10.80.1.0-24",
        "fixture_subnets": [
            {
                "subnet": "zone-10.80.1.0-24",
                "subnet_vnet": "target",
                "subnet_cidr": TARGET,
                "subnet_snat": initial,
            },
            {
                "subnet": "zone-10.80.2.0-24",
                "subnet_vnet": "otheron",
                "subnet_cidr": "10.80.2.0/24",
                "subnet_snat": 1,
            },
            {
                "subnet": "zone-10.80.3.0-24",
                "subnet_vnet": "otheroff",
                "subnet_cidr": "10.80.3.0/24",
                "subnet_snat": 0,
            },
        ],
        "fixture_rules": [
            {
                "snat_source": TARGET,
                "snat_out_iface": "vmbr0",
                "snat_target": "SNAT",
                "snat_count": initial,
            },
            {
                "snat_source": "10.80.2.0/24",
                "snat_out_iface": "vmbr0",
                "snat_target": "SNAT",
                "snat_count": 3,
            },
            {
                "snat_source": "10.80.3.0/24",
                "snat_out_iface": "vmbr0",
                "snat_target": "SNAT",
                "snat_count": 1,
            },
        ],
    }
    extra = tmp_path / "vars.json"
    extra.write_text(json.dumps(fixture))
    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("ansible-playbook")),
            "-i",
            str(inventory),
            str(wrapper),
            "-e",
            f"@{extra}",
        ],
        env={
            **os.environ,
            "RANGE42_ACTIVE_CONFIG_DIR": str(config),
            "ANSIBLE_ROLES_PATH": str(tmp_path / "roles"),
            "ANSIBLE_NOCOLOR": "1",
        },
        text=True,
        capture_output=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr
    return json.loads(output.read_text())


@pytest.mark.parametrize(
    ("mode", "initial", "desired"),
    [("on", 0, 1), ("off", 1, 0), ("toggle", 0, 1), ("toggle", 1, 0)],
)
def test_internet_change_does_not_reconcile_a_neighbours_declared_policy(
    tmp_path, mode, initial, desired
):
    result = run_bundle(tmp_path, mode, initial)
    assert result["reconciled"] == [{"cidr": TARGET, "want": desired}]
    assert result["actions"].count("network_apply_sdn") == 1


@pytest.mark.parametrize(("mode", "initial"), [("on", 1), ("off", 0)])
def test_already_matching_internet_state_does_not_rewrite_or_apply_cluster(
    tmp_path, mode, initial
):
    result = run_bundle(tmp_path, mode, initial)
    assert "network_update_sdn_subnet" not in result["actions"]
    assert "network_apply_sdn" not in result["actions"]
    assert result["reconciled"] == [{"cidr": TARGET, "want": initial}]


def run_network_bundle(tmp_path, bundle, *, drift=False, live_count=1):
    config = tmp_path / "config"
    (config / "secrets").mkdir(parents=True)
    (config / "secrets/default_vault.yml").write_text("proxmox_node: pve-test\n")
    role = tmp_path / "roles/range42-ansible_roles-proxmox_controller/tasks"
    role.mkdir(parents=True)
    (role / "main.yml").write_text("""- ansible.builtin.set_fact:
    observed_actions: "{{ observed_actions | default([]) + [proxmox_vm_action] }}"
- ansible.builtin.set_fact:
    network_list_sdn_zones: [{zone: zone}]
    network_list_sdn_vnets: [{vnet: target}]
    network_list_sdn_subnets: "{{ fixture_subnets }}"
  when: proxmox_vm_action in ['network_list_sdn_zones', 'network_list_sdn_vnets', 'network_list_sdn_subnets']
- ansible.builtin.set_fact:
    network_snat_snapshot:
      version: 1
      node: pve-test
      nat_counts: "{{ fixture_counts }}"
  when: proxmox_vm_action == 'network_snapshot_snat_rules'
- ansible.builtin.set_fact:
    observed_restoration: "{{ observed_restoration | default([]) + [{'excluded': sdn_snat_excluded_sources, 'allow_new': sdn_snat_allow_new_rules}] }}"
  when: proxmox_vm_action == 'network_restore_snat_snapshot'
""")
    inventory = tmp_path / "hosts.ini"
    inventory.write_text(
        f"proxmox ansible_connection=local ansible_python_interpreter={sys.executable}\n"
    )
    output = tmp_path / "observed.json"
    wrapper = tmp_path / "scenario.yml"
    wrapper.write_text(f"""- import_playbook: {ROOT}/bundles/proxmox/sdn_network.{bundle}/main.yml
- hosts: proxmox
  gather_facts: false
  tasks:
    - ansible.builtin.copy:
        dest: {output}
        content: "{{{{ {{'actions': observed_actions, 'restoration': observed_restoration | default([])}} | to_json }}}}"
""")
    fixture = {
        "BUNDLE_SDN_ZONE": "zone",
        "BUNDLE_SDN_VNETS": [
            {"vnet": "target", "subnet": TARGET, "gateway": "10.80.1.1", "snat": True}
        ],
        "fixture_subnets": [
            {
                "subnet": "zone-10.80.1.0-24",
                "subnet_vnet": "target",
                "subnet_cidr": TARGET,
                "subnet_gateway": "10.80.1.254" if drift else "10.80.1.1",
                "subnet_snat": 1,
            }
        ],
        "fixture_counts": {TARGET: live_count, "10.80.2.0/24": 3},
    }
    extra = tmp_path / "vars.json"
    extra.write_text(json.dumps(fixture))
    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("ansible-playbook")),
            "-i",
            str(inventory),
            str(wrapper),
            "-e",
            f"@{extra}",
        ],
        env={
            **os.environ,
            "RANGE42_ACTIVE_CONFIG_DIR": str(config),
            "ANSIBLE_ROLES_PATH": str(tmp_path / "roles"),
            "ANSIBLE_NOCOLOR": "1",
        },
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr
    return json.loads(output.read_text())


def test_stable_bootstrap_skips_global_apply(tmp_path):
    result = run_network_bundle(tmp_path, "bootstrap")
    assert "network_apply_sdn" not in result["actions"]
    assert result["restoration"] == []


@pytest.mark.parametrize(("drift", "live_count"), [(True, 1), (False, 0)])
def test_bootstrap_snapshots_before_writes_and_preserves_undeclared_sources(
    tmp_path, drift, live_count
):
    result = run_network_bundle(
        tmp_path, "bootstrap", drift=drift, live_count=live_count
    )
    assert result["actions"].count("network_apply_sdn") == 1
    assert result["actions"].index("network_snapshot_snat_rules") < result[
        "actions"
    ].index("network_apply_sdn")
    if drift:
        assert result["actions"].index("network_snapshot_snat_rules") < result[
            "actions"
        ].index("network_update_sdn_subnet")
    assert result["restoration"] == [{"excluded": [TARGET], "allow_new": False}]


def test_explicit_apply_preserves_prior_duplicates_without_erasing_new_pending_nat(
    tmp_path,
):
    result = run_network_bundle(tmp_path, "apply")
    assert result["actions"] == [
        "network_snapshot_snat_rules",
        "network_apply_sdn",
        "network_restore_snat_snapshot",
    ]
    assert result["restoration"] == [{"excluded": [], "allow_new": True}]
