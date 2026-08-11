# blank_scenario_2_subnets

Multi-subnet lab with 4 team VMs on 2 subnets (vmbr143 + vmbr144) plus an
admin platform (3 always-on deployer VMs + 2 optional admin VMs gated by
feature flags). Bundle-driven shape (mirror of `kunai_lab` /
`demo_lab`).

Anchor scenario for `blank_scenario_4_subnets` + `blank_scenario_6_subnets`
(both mirrors of bs2 with more subnets / more team VMs).

> Admin subnet uses dense IPs `.120-.124` on `192.168.142.0/24`. bs2 / bs4 / bs6 use
> non-overlapping admin IP ranges (`.120-.124`, `.130-.134`, `.140-.144`), and other
> scenarios sit on different ranges, so all of them can be deployed **in parallel** on
> the same Proxmox host without collision.

## Network architecture

```
                              +-----------------------+
                              |     Proxmox Host      |
                              +-----------+-----------+
                                          |
              +---------------+-----------+-----------+
              |               |                       |
           vmbr142          vmbr143                vmbr144
        (admin band)     (team subnet 1)        (team subnet 2)
              |               |                       |
   +----------+-------+   +---+---+               +---+---+
   |        admin     |   |  team |               |  team |
   | wazuh   .120 *   |   | 143.200|              | 144.200|
   | misp    .124 *   |   | 143.201|              | 144.201|
   | deployer-* .121  |   +-------+               +-------+
   | deployer-* .122  |
   | deployer-* .123  |
   +------------------+
       * optional (INSTALL_WAZUH / INSTALL_MISP, default NO)
```

## VM details

| VM Name                              | VM ID | IP              | Bridge  | Template                            | Gated by         |
|--------------------------------------|-------|-----------------|---------|-------------------------------------|------------------|
| bs2-team-143-01                      | 2001  | 192.168.143.200 | vmbr143 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-team-143-02                      | 2002  | 192.168.143.201 | vmbr143 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-team-144-01                      | 2003  | 192.168.144.200 | vmbr144 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-team-144-02                      | 2004  | 192.168.144.201 | vmbr144 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-admin-deployer-api-gateway       | 2121  | 192.168.142.121 | vmbr142 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-admin-deployer-api-backend       | 2122  | 192.168.142.122 | vmbr142 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-admin-deployer-ui                | 2123  | 192.168.142.123 | vmbr142 | template-vm-small-01-4g-32g (9221)  | always created   |
| bs2-admin-wazuh                      | 2120  | 192.168.142.120 | vmbr142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_WAZUH`  |
| bs2-admin-misp                       | 2124  | 192.168.142.124 | vmbr142 | template-vm-medium-02-8g-64g (9232) | `INSTALL_MISP`   |

Source of truth : `manifest/scenario_vms.json`.

## Feature flags

See `manifest/feature_flags.yml`. All flags default to `NO`.

| Flag                | Effect                                                          | Default |
|---------------------|-----------------------------------------------------------------|---------|
| `INSTALL_WAZUH`     | Deploy admin-wazuh SIEM + wazuh-agent on the 8 non-server VMs   | NO      |
| `INSTALL_MISP`      | Deploy admin-misp (docker-compose stack)                        | NO      |
| `INSTALL_TAILSCALE` | Tailscale VPN client on admin tier                              | NO      |

## Behavior change vs legacy `blank_scenario_2_subnets`

The legacy `blank_scenario_2_subnets` created `bs2-admin-wazuh` unconditionally
and installed the full Wazuh stack on it. The `_bundles` variant gates this
behind `INSTALL_WAZUH=YES` (default `NO`) for consistency with the rest of the
bundle-driven scenarios. An operator who wants the OLD behavior must pass
`-e INSTALL_WAZUH=YES`.

## Usage

```bash
range42-context use <codename> blank_scenario_2_subnets
range42-context deploy

# enable Wazuh SIEM :
./blank_scenario_2_subnets.setup.sh -e INSTALL_WAZUH=YES

# enable both Wazuh + MISP (MISP requires .env populated in the catalog
# before this command - see admin-misp.yml documentation) :
./blank_scenario_2_subnets.setup.sh -e INSTALL_WAZUH=YES -e INSTALL_MISP=YES
```

## Wrapper scripts

| Script                                                          | Action                                                              |
|-----------------------------------------------------------------|---------------------------------------------------------------------|
| `blank_scenario_2_subnets.setup.sh`                     | Run main playbook (templates + VMs + optional admin)                |
| `blank_scenario_2_subnets.setup_vms_only.sh`            | Run main_vms_only.yml (skip template creation)                      |
| `blank_scenario_2_subnets.reset.setup.sh`               | Delete + redeploy VMs                                               |
| `blank_scenario_2_subnets.reset.ssh_keys.sh`            | Clear ~/.ssh/known_hosts for every IP in manifest                   |
| `blank_scenario_2_subnets.delete_vms_only.sh`           | Delete VMs only, keep templates                                     |
| `blank_scenario_2_subnets.delete_all.sh`                | Delete VMs + templates (WARNING - affects other scenarios)          |
