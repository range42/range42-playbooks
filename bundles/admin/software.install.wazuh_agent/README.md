# bundles/admin/software.install.wazuh_agent

Wazuh agent install bundle - 1 play on every host of the wazuh clients group.

The agent is configured to report to the wazuh server (running the companion
bundle `bundles/admin/software.install.wazuh/`) via TCP/1514 + HTTPS API on
port 55000.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `wazuh_clients_group` | `r42_admin_wazuh_clients` | inventory group whose hosts get the agent |
| `global_vm_ci_ip` | `192.168.142.100` | IP of the wazuh server the agents report to |

## Vault loading

No vault keys required. The agent enrolment uses TCP/1514 with the manager
key exchange ; no admin password reads from this bundle.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/admin/software.install.wazuh_agent/main.yml"
  when: INSTALL_WAZUH | default("YES") | upper == "YES"
  vars:
    wazuh_clients_group: "r42_admin_wazuh_clients"
    global_vm_ci_ip:     "192.168.142.100"
```

## Naming convention

Mirrors the catalog sub-role `range42-catalog/02_ansible_layer/admin/roles/software.install.wazuh/roles/wazuh/ansible-wazuh-agent`.
The bundle is a thin orchestrator on top of that sub-role for the clients
group. Server install lives in the companion bundle `software.install.wazuh/`.
