# bundles/admin/software.install.wazuh_agent

Wazuh agent install bundle - 1 play on every host of the wazuh clients group,
which starts with a preflight check of the vault.

The agent enrolls on the wazuh server (running the companion bundle
`bundles/admin/software.install.wazuh/`) on TCP/1515 with the enrollment
password, then reports on TCP/1514. It does not call the manager API
(TCP/55000).

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `wazuh_clients_group` | `r42_admin_wazuh_clients` | inventory group whose hosts get the agent |
| `global_vm_ci_ip` | `192.168.142.100` | IP of the wazuh server the agents report to |

## Vault loading

The bundle reads `$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml`.
Required key : `infrastructure_wazuh_authd_password`, the enrollment password
that the server bundle sets on the manager (authd `use_password`). The
preflight task fails when the key is missing, empty or a `REPLACE_ME`
placeholder, and prints only the key name.

The enrollment is the agent's own `<enrollment>` block (the vendored role's
default), not `agent-auth` : the role writes the password to
`/var/ossec/etc/authd.pass` (owner `wazuh`, mode `0640`) and the agent reads it
at its first start. The password is never on a command line, and not in the
Ansible output at any verbosity (`--diff` would show the file content). Residual exposure : the file stays on every agent host, so whoever
gets root or the `wazuh` group on an agent host can read it and enroll other
agents ; tcp 1514/1515 of the manager accept only the agent sources (ufw).

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.wazuh_agent/main.yml"
  when: INSTALL_WAZUH | default("YES") | upper == "YES"
  vars:
    wazuh_clients_group: "r42_admin_wazuh_clients"
    global_vm_ci_ip:     "192.168.142.100"
```

## Naming convention

Mirrors the catalog sub-role `range42-catalog/02_ansible_layer/admin/roles/software.install.wazuh/roles/wazuh/ansible-wazuh-agent`.
The bundle is a thin orchestrator on top of that sub-role for the clients
group. Server install lives in the companion bundle `software.install.wazuh/`.
