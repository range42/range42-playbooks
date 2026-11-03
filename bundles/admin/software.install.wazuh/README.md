# bundles/admin/software.install.wazuh

Wazuh server stack install bundle - 8 plays on the wazuh server host :

1. preflight (the four vault keys below are set, the firewall sources are explicit), then
   configure the firewall (ufw, default deny ; see "Ports and sources")
2. install wazuh-indexer + JVM tuning + cluster bootstrap
3. wait for indexer API on port 9200
4. install wazuh-dashboard (API user `wazuh-wui` with the vault password)
5. install wazuh-manager (enrollment requires the vault password) + wazuh-filebeat-oss
6. wait for manager API on port 55000 + daemons ready
7. replace the passwords of the API users `wazuh` and `wazuh-wui` (upstream default : the user
   name) with the vault values, then check that the defaults are refused
8. run wazuh-passwords-tool.sh to set the admin password from the vault

Companion bundle `bundles/admin/software.install.wazuh_agent/` installs the
agent on client hosts and points them at this server.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-wazuh` | inventory hostname of the wazuh server VM |
| `global_vm_ci_ip` | `192.168.142.100` | IP of the wazuh server (used for indexer cluster, manager filebeat output) |
| `wazuh_agent_sources` | `["192.168.142.112", "192.168.144.170"]` | agent hosts : tcp 1514 (events) and 1515 (enrollment) |
| `wazuh_dashboard_sources` | `["192.168.142.1"]` | operator path to the dashboard : tcp 443 |

Optional : `wazuh_api_sources` (default `[]`) : hosts allowed to call the manager API on tcp
55000.

Each source is an IPv4 address or a CIDR of /8 to /32. The preflight refuses an empty agent or
dashboard list, `all`, `any` and /0 : the bundle has no open default.

## Ports and sources

ufw on the manager, default deny for every other inbound port :

| Port | Source | Why |
|---|---|---|
| tcp 22 | any | deploy and operator SSH (SSH baseline) |
| tcp 443 | `wazuh_dashboard_sources` | the dashboard |
| tcp 1514-1515 | `wazuh_agent_sources` | agent events (1514) and enrollment (1515, with the password) |
| tcp 55000 | `wazuh_api_sources` (default none) | the manager API. The dashboard and this bundle call it on 127.0.0.1 ; the agents enroll on 1515 and do not need it |

These rules apply without the Proxmox VM firewall. The Proxmox accepts declared by the
scenarios stay a second layer, active only once armed.

## Vault loading

Each play loads the scenario's vault from
`$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml` (env var exported by
`range42-context use`). Required keys :

| Key | Use |
|---|---|
| `infrastructure_wazuh_admin_password` | dashboard / indexer user `admin` |
| `infrastructure_wazuh_authd_password` | agent enrollment (authd `use_password: yes`), tcp 1515 |
| `infrastructure_wazuh_api_password` | API user `wazuh` |
| `infrastructure_wazuh_wui_password` | API user `wazuh-wui`, which the dashboard uses |

`range42-context init` generates them. A workspace created before the last three existed lacks
them : the preflight tasks (first tasks of the first play) stop the run before the bundle
changes anything, and name the missing key. They run on the manager host, not on localhost, so
that a run with `--limit` cannot skip them. Recreate the
workspace, or add the keys with `ansible-vault edit` (20 to 64 characters of `a-z A-Z 0-9 - _`
with an upper case letter, a lower case letter, a digit and a `-` or `_`).

The tasks that handle a vault value or an API token run with `no_log: true` : the API calls,
the passwords tool and the authd password file (vendored task).

## A manager that is already running

The bundle is written for a fresh deploy. A manager installed by an earlier version of this
bundle keeps open enrollment, the default API passwords and the open ufw rules until it is
redeployed. To fix one by hand, on the manager :

1. Enrollment password : write the vault value to `/var/ossec/etc/authd.pass` (owner `wazuh`,
   group `wazuh`, mode `0640`), set `<use_password>yes</use_password>` in the `<auth>` block of
   `/var/ossec/etc/ossec.conf`, restart `wazuh-manager`. The agents already enrolled keep their
   keys ; a new agent needs the password.
2. API passwords : log in as `wazuh` (`POST /security/user/authenticate`), then
   `PUT /security/users/<id>` with `{"password": "..."}` for `wazuh-wui`, then for `wazuh`.
   Write the new `wazuh-wui` password in `/usr/share/wazuh-dashboard/data/wazuh/config/wazuh.yml`
   (`hosts` entry `default`).
3. ufw : replace the `any` rules on 443, 1514, 1515 and 55000 with rules from the sources above.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.wazuh/main.yml"
  when: INSTALL_WAZUH | default("YES") | upper == "YES"
  vars:
    global_vm_ssh_name:      "r42.admin-wazuh"
    global_vm_ci_ip:         "192.168.142.100"
    wazuh_agent_sources:     ["192.168.142.112", "192.168.144.170"]
    wazuh_dashboard_sources: ["192.168.142.1"]
```

## Naming convention

Mirrors the catalog role `range42-catalog/02_ansible_layer/admin/roles/software.install.wazuh`
which contains the wazuh sub-roles (indexer, dashboard, manager, filebeat-oss).
The bundle orchestrates them on the server host ; the catalog role provides
the building blocks.
