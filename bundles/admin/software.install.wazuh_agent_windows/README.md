# software.install.wazuh_agent_windows (bundle)

Thin bundle: invokes the catalog role `software.install.wazuh_agent_windows` on a target group of
Windows hosts : downloads the pinned Wazuh agent MSI (4.14.4) to `%TEMP%` of the connection
account, checks its SHA-256, installs it with `WAZUH_MANAGER`, `WAZUH_REGISTRATION_SERVER` and
`WAZUH_AGENT_NAME`, and keeps the service `WazuhSvc` running with start type automatic. No
`become`, no fact gathering. The Linux agent is `admin/software.install.wazuh_agent`, the server
`admin/software.install.wazuh`.

Caller vars: `TARGET_GROUP`, `WAZUH_MANAGER`, `WAZUH_AGENT_NAME` (required) ;
`WAZUH_REGISTRATION_SERVER` (def `""` = `WAZUH_MANAGER`). No secret, no vault. Details : the role
README in range42-catalog.

Enrollment uses no password : any host that reaches tcp 1515 of the manager can enroll an agent.
Restrict tcp 1514 and 1515 of the manager to the agent addresses with a network firewall.

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.wazuh_agent_windows/main.yml"
  vars:
    TARGET_GROUP: "r42_example_windows"
    WAZUH_MANAGER: "192.0.2.10"
    WAZUH_AGENT_NAME: "{{ inventory_hostname }}"
```
