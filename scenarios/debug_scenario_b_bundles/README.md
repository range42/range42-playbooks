# debug_scenario_b_bundles

Minimal debug/dev scenario - 1 Alpine VM on 1 subnet. Same shape as
debug_scenario_a but on a different subnet (vmbr148), used to verify
multi-scenario coexistence on a single Proxmox. Bundle-driven shape (mirror
of `kunai_lab_bundles` / `demo_lab_bundles`) with optional admin tier (Wazuh
SIEM + MISP threat intel) gated by feature flags.

## Network architecture

```
                              +-----------------------+
                              |     Proxmox Host      |
                              +-----------+-----------+
                                          |
                          +---------------+---------------+
                          |                               |
                       vmbr142                         vmbr148
                    (admin band)                      (debug B)
                          |                               |
                  +-------+--------+              +-------+--------+
                  | 192.168.142/24 |              | 192.168.148/24 |
                  |                |              |                |
                  | admin-wazuh .155 (optional)   | dsb-vm-01 .250 |
                  | admin-misp  .156 (optional)   |                |
                  +----------------+              +----------------+
```

## VM details

| VM Name      | VM ID | IP              | Bridge  | Template                            | Gated by         |
|--------------|-------|-----------------|---------|-------------------------------------|------------------|
| dsb-vm-01    | 8501  | 192.168.148.250 | vmbr148 | template-vm-alpine-nano (9903)      | always created   |
| admin-wazuh  | 8550  | 192.168.142.155 | vmbr142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH`  |
| admin-misp   | 8551  | 192.168.142.156 | vmbr142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_MISP`   |

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                    | Default |
|---------------------|-----------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on dsb-vm-01        | NO      |
| `INSTALL_MISP`      | Deploy admin-misp (docker-compose stack)                  | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                        | NO      |

## Usage

```bash
range42-context use <codename> debug_scenario_b
range42-context deploy

# enable Wazuh SIEM :
./debug_scenario_b_bundles.setup.sh -e INSTALL_WAZUH=YES

# enable both Wazuh + MISP (MISP requires .env populated in the catalog
# before this command - see admin-misp.yml documentation) :
./debug_scenario_b_bundles.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script                                            | Action                                                              |
|---------------------------------------------------|---------------------------------------------------------------------|
| `debug_scenario_b_bundles.setup.sh`               | Run main playbook (templates + VMs + optional admin)                |
| `debug_scenario_b_bundles.setup_vms_only.sh`      | Run main_vms_only.yml (skip template creation)                      |
| `debug_scenario_b_bundles.reset.setup.sh`         | Delete + redeploy VMs                                               |
| `debug_scenario_b_bundles.reset.ssh_keys.sh`      | Clear ~/.ssh/known_hosts for every IP in manifest                   |
| `debug_scenario_b_bundles.delete_vms_only.sh`     | Delete VMs only, keep templates                                     |
| `debug_scenario_b_bundles.delete_all.sh`          | Delete VMs + templates (alpine-nano 9903 + medium 9232)             |
