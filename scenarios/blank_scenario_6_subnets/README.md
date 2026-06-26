# blank_scenario_6_subnets_bundles

Multi-subnet lab with 24 team VMs on 6 subnets (vmbr143-148, 4 VMs per subnet)
plus an admin platform (3 always-on deployer VMs + 2 optional admin VMs gated
by feature flags). Bundle-driven shape (mirror of `blank_scenario_4_subnets_bundles`).

> Admin subnet uses dense IPs `.140-.144` on `192.168.142.0/24` (vs bs2's
> `.120-.124`, bs4's `.130-.134`). All three blank scenarios use non-overlapping
> admin IP ranges, so they can be deployed in parallel on the same Proxmox host.
>
> bs6 is the only blank sibling using vmbr147 + vmbr148. These bridges are
> also used by `debug_scenario_a` (.147.250) and `debug_scenario_b` (.148.250) ;
> bs6 team IPs are .220-.223 so no collision with the debug scenarios.

## VM details (29 VMs)

| Tier | VM Name | VM ID | IP | Bridge | Template | Gated by |
|---|---|---|---|---|---|---|
| team | bs6-team-143-01..04 | 6001-6004 | 192.168.143.220-223 | vmbr143 | small-01 (9221) | always |
| team | bs6-team-144-01..04 | 6005-6008 | 192.168.144.220-223 | vmbr144 | small-01 (9221) | always |
| team | bs6-team-145-01..04 | 6009-6012 | 192.168.145.220-223 | vmbr145 | small-01 (9221) | always |
| team | bs6-team-146-01..04 | 6013-6016 | 192.168.146.220-223 | vmbr146 | small-01 (9221) | always |
| team | bs6-team-147-01..04 | 6017-6020 | 192.168.147.220-223 | vmbr147 | small-01 (9221) | always |
| team | bs6-team-148-01..04 | 6021-6024 | 192.168.148.220-223 | vmbr148 | small-01 (9221) | always |
| admin | bs6-admin-deployer-api-gateway | 6141 | 192.168.142.141 | vmbr142 | small-01 (9221) | always |
| admin | bs6-admin-deployer-api-backend | 6142 | 192.168.142.142 | vmbr142 | small-01 (9221) | always |
| admin | bs6-admin-deployer-ui | 6143 | 192.168.142.143 | vmbr142 | small-01 (9221) | always |
| admin | bs6-admin-wazuh | 6140 | 192.168.142.140 | vmbr142 | medium-02 (9232) | `INSTALL_WAZUH` |
| admin | bs6-admin-misp | 6144 | 192.168.142.144 | vmbr142 | medium-02 (9232) | `INSTALL_MISP` |

Source of truth : `manifest/scenario_vms.json`.

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                            | Default |
|---------------------|-------------------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on the 27 non-server VMs    | NO      |
| `INSTALL_MISP`      | Deploy admin-misp (docker-compose stack)                          | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                                | NO      |

## Behavior change vs legacy `blank_scenario_6_subnets`

The legacy scenario created `bs6-admin-wazuh` unconditionally. The `_bundles`
variant gates this behind `INSTALL_WAZUH=YES` (default `NO`). Operator who
wants the OLD behavior must pass `-e INSTALL_WAZUH=YES`.

## Usage

```bash
range42-context use <codename> blank_scenario_6_subnets
range42-context deploy

# enable Wazuh SIEM :
./blank_scenario_6_subnets_bundles.setup.sh -e INSTALL_WAZUH=YES

# enable both :
./blank_scenario_6_subnets_bundles.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script | Action |
|---|---|
| `blank_scenario_6_subnets_bundles.setup.sh` | Full deploy (templates + VMs + optional admin) |
| `blank_scenario_6_subnets_bundles.setup_vms_only.sh` | VMs only (skip templates) |
| `blank_scenario_6_subnets_bundles.reset.setup.sh` | Delete + redeploy |
| `blank_scenario_6_subnets_bundles.reset.ssh_keys.sh` | Clear known_hosts for manifest IPs |
| `blank_scenario_6_subnets_bundles.delete_vms_only.sh` | Delete VMs only, keep templates |
| `blank_scenario_6_subnets_bundles.delete_all.sh` | Delete VMs + templates (WARNING - shared) |
