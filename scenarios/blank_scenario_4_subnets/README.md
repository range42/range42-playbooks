# blank_scenario_4_subnets

Multi-subnet lab with 16 team VMs on 4 subnets (vmbr143-146, 4 VMs per subnet)
plus an admin platform (3 always-on deployer VMs + 2 optional admin VMs gated
by feature flags). Bundle-driven shape (mirror of `blank_scenario_2_subnets`).

> Admin subnet uses dense IPs `.130-.134` on `192.168.142.0/24` (vs bs2's
> `.120-.124`, bs6's `.140-.144`). All three blank scenarios use non-overlapping
> admin IP ranges, so they can be deployed in parallel on the same Proxmox host.

## VM details (21 VMs)

| Tier | VM Name | VM ID | IP | Bridge | Template | Gated by |
|---|---|---|---|---|---|---|
| team | bs4-team-143-01..04 | 4001-4004 | 192.168.143.210-213 | vmbr143 | small-01 (9221) | always |
| team | bs4-team-144-01..04 | 4005-4008 | 192.168.144.210-213 | vmbr144 | small-01 (9221) | always |
| team | bs4-team-145-01..04 | 4009-4012 | 192.168.145.210-213 | vmbr145 | small-01 (9221) | always |
| team | bs4-team-146-01..04 | 4013-4016 | 192.168.146.210-213 | vmbr146 | small-01 (9221) | always |
| admin | bs4-admin-deployer-api-gateway | 4131 | 192.168.142.131 | vmbr142 | small-01 (9221) | always |
| admin | bs4-admin-deployer-api-backend | 4132 | 192.168.142.132 | vmbr142 | small-01 (9221) | always |
| admin | bs4-admin-deployer-ui | 4133 | 192.168.142.133 | vmbr142 | small-01 (9221) | always |
| admin | bs4-admin-wazuh | 4130 | 192.168.142.130 | vmbr142 | medium-02 (9232) | `INSTALL_WAZUH` |
| admin | bs4-admin-misp | 4134 | 192.168.142.134 | vmbr142 | medium-02 (9232) | `INSTALL_MISP` |

Source of truth : `manifest/scenario_vms.json`.

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                            | Default |
|---------------------|-------------------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on the 19 non-server VMs    | NO      |
| `INSTALL_MISP`      | Deploy admin-misp (docker-compose stack)                          | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                                | NO      |

## Behavior change vs legacy `blank_scenario_4_subnets`

The legacy scenario created `bs4-admin-wazuh` unconditionally. The `_bundles`
variant gates this behind `INSTALL_WAZUH=YES` (default `NO`). Operator who
wants the OLD behavior must pass `-e INSTALL_WAZUH=YES`.

## Usage

```bash
range42-context use <codename> blank_scenario_4_subnets
range42-context deploy

# enable Wazuh SIEM :
./blank_scenario_4_subnets.setup.sh -e INSTALL_WAZUH=YES

# enable both :
./blank_scenario_4_subnets.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script | Action |
|---|---|
| `blank_scenario_4_subnets.setup.sh` | Full deploy (templates + VMs + optional admin) |
| `blank_scenario_4_subnets.setup_vms_only.sh` | VMs only (skip templates) |
| `blank_scenario_4_subnets.reset.setup.sh` | Delete + redeploy |
| `blank_scenario_4_subnets.reset.ssh_keys.sh` | Clear known_hosts for manifest IPs |
| `blank_scenario_4_subnets.delete_vms_only.sh` | Delete VMs only, keep templates |
| `blank_scenario_4_subnets.delete_all.sh` | Delete VMs + templates (WARNING - shared) |
