# software.install.wazuh_agent_windows (bundle)

Thin bundle: invokes the catalog role `software.install.wazuh_agent_windows` on a target group of
Windows hosts : downloads the pinned Wazuh agent MSI (4.14.4) to `%TEMP%` of the connection
account, checks its SHA-256, installs it with `WAZUH_MANAGER`, `WAZUH_REGISTRATION_SERVER`,
`WAZUH_AGENT_NAME` and, when the vault has the key, `WAZUH_REGISTRATION_PASSWORD`, and keeps the service `WazuhSvc` running with start type automatic. No
`become`, no fact gathering. The Linux agent is `admin/software.install.wazuh_agent`, the server
`admin/software.install.wazuh`.

Caller vars: `TARGET_GROUP`, `WAZUH_MANAGER`, `WAZUH_AGENT_NAME` (required) ;
`WAZUH_REGISTRATION_SERVER` (def `""` = `WAZUH_MANAGER`). Details : the role README in
range42-catalog.

Vault : the bundle reads `$RANGE42_ACTIVE_CONFIG_DIR/secrets/default_vault.yml` and passes
`infrastructure_wazuh_authd_password` as `WAZUH_REGISTRATION_PASSWORD`, the enrollment password
the server bundle sets on the manager (authd `use_password`). Without that key the password is
empty and the agent enrolls without one : only a manager without `use_password` accepts it. A
manager without `use_password` refuses an agent that sends a password (wazuh-authd 4.14.4,
`src/os_auth/auth.c`) : the vault key and the server bundle go together.

The role installs the MSI with `no_log: true` : the password is not in the Ansible output, but it
is on the `msiexec` command line while the installer runs. The agent keeps it on disk after the
install, in `C:\Program Files (x86)\ossec-agent\authd.pass`, readable only by `SYSTEM` and
`Administrators` (agent 4.14.4, see the role README).

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.wazuh_agent_windows/main.yml"
  vars:
    TARGET_GROUP: "r42_example_windows"
    WAZUH_MANAGER: "192.0.2.10"
    WAZUH_AGENT_NAME: "{{ inventory_hostname }}"
```
