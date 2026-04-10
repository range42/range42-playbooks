# blank_scenario_2_subnets

Minimal network lab — 2 team subnets, 2 VMs each. Optional admin subnet with wazuh + deployer platform.

> **DEPLOY_ADMIN_INFRASTRUCTURE: NO** (default) — admin VMs are commented out. Uncomment in `main.yml` and `01_admin_infrastructure/_main.yml` to deploy.

## Network architecture

```
                              ┌───────────────────────────┐
                              │       Proxmox Host        │
                              │      (ip_forward=1)       │
                              └──┬──────────┬─────────┬───┘
                                 │          │         │
                           vmbr142     vmbr143     vmbr144
                           (admin)     (team A)    (team B)
                                 │          │         │
    ┌────────────────────────────┘          │         └────────────────────────────┐
    │                          ┌────────────┘                                     │
    │                          │                                                  │
┌───┴──────────────────┐  ┌───┴──────────────────┐  ┌────────────────────────────┴┐
│ Admin (optional)     │  │ Team A               │  │ Team B                      │
│ 192.168.142.0/24     │  │ 192.168.143.0/24     │  │ 192.168.144.0/24            │
│                      │  │                      │  │                             │
│ wazuh          .100  │  │ team-143-01    .200  │  │ team-144-01          .200   │
│ api-gateway    .120  │  │ team-143-02    .201  │  │ team-144-02          .201   │
│ api-backend    .121  │  │                      │  │                             │
│ deployer-ui    .123  │  │                      │  │                             │
│ (all commented out)  │  │                      │  │                             │
└──────────────────────┘  └──────────────────────┘  └─────────────────────────────┘
```

## Team VMs

| VM | VM ID | IP | Bridge |
|----|-------|----|--------|
| bs2-team-143-01 | 5001 | 192.168.143.200 | vmbr143 |
| bs2-team-143-02 | 5002 | 192.168.143.201 | vmbr143 |
| bs2-team-144-01 | 5003 | 192.168.144.200 | vmbr144 |
| bs2-team-144-02 | 5004 | 192.168.144.201 | vmbr144 |

## Admin VMs (optional, commented out)

| VM | VM ID | IP | Bridge |
|----|-------|----|--------|
| admin-wazuh | 5100 | 192.168.142.100 | vmbr142 |
| admin-deployer-api-gateway | 5101 | 192.168.142.120 | vmbr142 |
| admin-deployer-api-backend | 5102 | 192.168.142.121 | vmbr142 |
| admin-deployer-ui | 5103 | 192.168.142.123 | vmbr142 |

## Stages

- **stage_00** — VM creation (clone template + cloud-init + start)
- **stage_01** — Basic packages, dotfiles, firewall (SSH only)

## Scripts

| Script | What it does |
|--------|-------------|
| `blank_scenario_2_subnets.setup.sh` | Full deploy (templates + VMs + software) |
| `blank_scenario_2_subnets.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `blank_scenario_2_subnets.delete_all.sh` | Destroy everything + clean SSH known_hosts |
| `blank_scenario_2_subnets.delete_vms_only.sh` | Destroy VMs only (keep templates) |
| `blank_scenario_2_subnets.reset.setup.sh` | Delete all + redeploy from scratch |
