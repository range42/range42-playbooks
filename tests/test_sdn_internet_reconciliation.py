"""Execute NAT bundles with a role boundary fixture; never run host networking."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sdn_controller_fixture import CLUSTER_SNAPSHOT, RECONCILE

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("mode", "initial", "desired"),
    [("on", 0, 1), ("off", 1, 0), ("toggle", 0, 1), ("toggle", 1, 0)],
)
def test_apply_preserves_other_subnets_and_reconciles_only_the_target(
    tmp_path, mode, initial, desired
):
    """Global apply side effects must use exact preservation, not other subnets' policy."""
    config = tmp_path / "config"
    (config / "secrets").mkdir(parents=True)
    (config / "secrets/default_vault.yml").write_text("proxmox_node: pve\n")
    role = tmp_path / "roles/range42-ansible_roles-proxmox_controller/tasks"
    role.mkdir(parents=True)
    # Only the controller boundary is substituted. Real Ansible imports, loop
    # scopes, target selection and caller variables execute from the bundle.
    (role / "main.yml").write_text(
        """- ansible.builtin.set_fact:
    network_list_sdn_subnets: "{{ fixture_subnets }}"
  when: proxmox_vm_action == 'network_list_sdn_subnets'
- ansible.builtin.set_fact:
    observed_updates: "{{ observed_updates | default([]) + [{'subnet': sdn_subnet_id, 'snat': sdn_subnet_snat | int}] }}"
  when: proxmox_vm_action == 'network_update_sdn_subnet'
- ansible.builtin.set_fact:
    observed_applies: "{{ observed_applies | default(0) | int + 1 }}"
  when: proxmox_vm_action == 'network_apply_sdn'
- ansible.builtin.set_fact:
    network_snat_snapshot:
      version: 1
      node: pve-test
      nat_counts: "{{ fixture_rules | items2dict(key_name='snat_source', value_name='snat_count') }}"
  when: proxmox_vm_action == 'network_snapshot_snat_rules'
- ansible.builtin.set_fact:
    observed_restoration: "{{ observed_restoration | default([]) + [sdn_snat_excluded_sources] }}"
  when: proxmox_vm_action == 'network_restore_snat_snapshot'
"""
        + CLUSTER_SNAPSHOT
        + RECONCILE
    )
    subnet_id = "zone-10.80.1.0-24"
    fixture = [
        {
            "subnet": subnet_id,
            "subnet_vnet": "target",
            "subnet_cidr": "10.80.1.0/24",
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
        {"subnet": "unknown-cidr", "subnet_vnet": "unknown"},
        {"subnet": "empty-cidr", "subnet_vnet": "empty", "subnet_cidr": ""},
    ]
    inventory = tmp_path / "hosts.ini"
    inventory.write_text(
        f"proxmox ansible_connection=local ansible_python_interpreter={sys.executable}\n"
    )
    result_path = tmp_path / "observed.json"
    wrapper = tmp_path / "scenario.yml"
    wrapper.write_text(f"""- import_playbook: {ROOT}/bundles/proxmox/sdn_network.internet_{mode}/main.yml
- hosts: proxmox
  gather_facts: false
  tasks:
    - ansible.builtin.copy:
        dest: {result_path}
        content: "{{{{ {{'updates': observed_updates, 'applies': observed_applies, 'reconciled': observed_reconciliation}} | to_json }}}}"
""")
    extra = tmp_path / "vars.json"
    extra.write_text(
        json.dumps(
            {
                "BUNDLE_SDN_SUBNET_ID": subnet_id,
                "fixture_subnets": fixture,
                "fixture_rules": [
                    {
                        "snat_source": row["subnet_cidr"],
                        "snat_count": row["subnet_snat"],
                    }
                    for row in fixture
                    if row.get("subnet_cidr")
                ],
            }
        )
    )
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
    observed = json.loads(result_path.read_text())
    assert observed["updates"] == [{"subnet": subnet_id, "snat": desired}]
    assert int(observed["applies"]) == 1
    assert observed["reconciled"] == [
        {"cidr": "10.80.1.0/24", "want": desired},
    ]
