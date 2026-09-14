"""Single-node controller facts for tests that replace the controller boundary."""

CLUSTER_SNAPSHOT = """
- ansible.builtin.set_fact:
    network_list_sdn_vnets: [{vnet: target, vnet_zone: zone}]
  when: proxmox_vm_action == 'network_list_sdn_vnets'
- ansible.builtin.set_fact:
    network_snat_snapshot_verified: true
    network_snat_apply_attempted: false
    network_snat_apply_verified: false
    network_snat_plan_input:
      desired_sources: "{{ sdn_snat_desired_sources }}"
      new_zones: "{{ sdn_snat_new_zones }}"
    network_snat_plan:
      version: 1
      nodes:
        - node: pve-test
          host: proxmox
          targets: >-
            {%- set targets = [] -%}
            {%- for desired in sdn_snat_desired_sources -%}
            {%- set _ = targets.append({'source': desired.source, 'want': desired.want}) -%}
            {%- endfor -%}
            {{ targets }}
    network_snat_snapshots: "{{ {'pve-test': network_snat_snapshot} }}"
    network_snat_reload_baseline: {pve-test: {upids: []}}
  when: proxmox_vm_action == 'network_snapshot_snat_rules'
"""

RECONCILE = """
- ansible.builtin.set_fact:
    observed_reconciliation: "{{ observed_reconciliation | default([]) + [{'cidr': _fixture_target.source, 'want': _fixture_target.want | int}] }}"
  loop: "{{ network_snat_plan.nodes[0].targets | default([]) }}"
  loop_control:
    loop_var: _fixture_target
  when: proxmox_vm_action == 'network_reconcile_snat_sources'
"""
