# bundles/admin/software.install.wazuh

Wazuh server stack install bundle - 7 plays on the wazuh server host :

1. configure firewall (ports 22, 443, 1515, 1514)
2. install wazuh-indexer + JVM tuning + cluster bootstrap
3. wait for indexer API on port 9200
4. install wazuh-dashboard
5. install wazuh-manager + wazuh-filebeat-oss
6. wait for manager API on port 55000 + daemons ready
7. run wazuh-passwords-tool.sh to set the admin password from the vault

Companion bundle `bundles/admin/software.install.wazuh-agent/` installs the
agent on client hosts and points them at this server.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-wazuh` | inventory hostname of the wazuh server VM |
| `global_vm_ci_ip` | `192.168.142.100` | IP of the wazuh server (used for indexer cluster, manager filebeat output) |

## Vault loading

Each play loads the scenario's vault from
`$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml` (env var exported by
`range42-context use`). Required key : `infrastructure_wazuh_admin_password`.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/admin/software.install.wazuh/main.yml"
  when: INSTALL_WAZUH | default("YES") | upper == "YES"
  vars:
    global_vm_ssh_name: "r42.admin-wazuh"
    global_vm_ci_ip:    "192.168.142.100"
```

## Naming convention

Mirrors the catalog role `range42-catalog/02_ansible_layer/admin/roles/software.install.wazuh`
which contains the wazuh sub-roles (indexer, dashboard, manager, filebeat-oss).
The bundle orchestrates them on the server host ; the catalog role provides
the building blocks.
