# debug_scenario_a

Minimal debug/dev scenario - 1 Alpine VM on 1 subnet. Designed for fast
iteration. Bundle-driven shape (mirror of `kunai_lab` /
`demo_lab`) with optional admin tier (Wazuh SIEM + MISP threat intel)
gated by feature flags.

## Network architecture

```
                              +-----------------------+
                              |     Proxmox Host      |
                              +-----------+-----------+
                                          |
                          +---------------+---------------+
                          |                               |
                       vmbr142                         vmbr147
                    (admin band)                      (debug A)
                          |                               |
                  +-------+--------+              +-------+--------+
                  | 192.168.142/24 |              | 192.168.147/24 |
                  |                |              |                |
                  | admin-wazuh .150 (optional)   | dsa-vm-01 .250 |
                  | admin-misp  .151 (optional)   |                |
                  +----------------+              +----------------+
```

## VM details

| VM Name      | VM ID | IP              | Bridge  | Template                            | Gated by         |
|--------------|-------|-----------------|---------|-------------------------------------|------------------|
| dsa-vm-01    | 8001  | 192.168.147.250 | vmbr147 | template-vm-alpine-nano (9903)      | always created   |
| admin-wazuh  | 8050  | 192.168.142.150 | vmbr142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH`  |
| admin-misp   | 8051  | 192.168.142.151 | vmbr142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_MISP`   |

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag             | Effect                                                    | Default |
|------------------|-----------------------------------------------------------|---------|
| `INSTALL_WAZUH`  | Deploy admin-wazuh SIEM + wazuh-agent on dsa-vm-01        | NO      |
| `INSTALL_MISP`   | Deploy admin-misp (docker-compose stack)                  | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                     | NO      |

## Usage

```bash
range42-context use <codename> debug_scenario_a
range42-context deploy

# enable Wazuh SIEM :
./debug_scenario_a.setup.sh -e INSTALL_WAZUH=YES

# enable both Wazuh + MISP (MISP requires .env populated in the catalog
# before this command - see admin-misp.yml documentation) :
./debug_scenario_a.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script                                            | Action                                                              |
|---------------------------------------------------|---------------------------------------------------------------------|
| `debug_scenario_a.setup.sh`               | Run main playbook (templates + VMs + optional admin)                |
| `debug_scenario_a.setup_vms_only.sh`      | Run main_vms_only.yml (skip template creation)                      |
| `debug_scenario_a.reset.setup.sh`         | Delete + redeploy VMs                                               |
| `debug_scenario_a.reset.ssh_keys.sh`      | Clear ~/.ssh/known_hosts for every IP in manifest                   |
| `debug_scenario_a.delete_vms_only.sh`     | Delete VMs only, keep templates                                     |
| `debug_scenario_a.delete_all.sh`          | Delete VMs + templates (alpine-nano 9903 + medium 9232)             |
