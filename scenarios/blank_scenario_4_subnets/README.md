# blank_scenario_4_subnets

Minimal network lab — 4 team subnets, 4 VMs each (16 VMs). Optional admin subnet with wazuh + deployer platform.

> **DEPLOY_ADMIN_INFRASTRUCTURE: NO** (default) — admin VMs are commented out. Uncomment in `main.yml` and `01_admin_infrastructure/_main.yml` to deploy.

## Network architecture

```
                                        ┌───────────────────────────┐
                                        │       Proxmox Host        │
                                        │      (ip_forward=1)       │
                                        └┬──────┬──────┬──────┬──────┬┘
                                         │      │      │      │      │
                                   vmbr142 vmbr143 vmbr144 vmbr145 vmbr146
                                   (admin) (team)  (team)  (team)  (team)
                                         │      │      │      │      │
┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│ Admin (optional)   │ │ Team A             │ │ Team B             │ │ Team C             │ │ Team D             │
│ 192.168.142.0/24   │ │ 192.168.143.0/24   │ │ 192.168.144.0/24   │ │ 192.168.145.0/24   │ │ 192.168.146.0/24   │
│                    │ │                    │ │                    │ │                    │ │                    │
│ wazuh        .100  │ │ team-143-01  .210  │ │ team-144-01  .210  │ │ team-145-01  .210  │ │ team-146-01  .210  │
│ api-gw       .120  │ │ team-143-02  .211  │ │ team-144-02  .211  │ │ team-145-02  .211  │ │ team-146-02  .211  │
│ api-back     .121  │ │ team-143-03  .212  │ │ team-144-03  .212  │ │ team-145-03  .212  │ │ team-146-03  .212  │
│ deployer-ui  .123  │ │ team-143-04  .213  │ │ team-144-04  .213  │ │ team-145-04  .213  │ │ team-146-04  .213  │
│ (commented out)    │ │                    │ │                    │ │                    │ │                    │
└────────────────────┘ └────────────────────┘ └────────────────────┘ └────────────────────┘ └────────────────────┘
```

## Team VMs (16 total)

| Subnet | VMs | VM IDs | IPs |
|--------|-----|--------|-----|
| vmbr143 | bs4-team-143-{01..04} | 6001-6004 | 192.168.143.{210..213} |
| vmbr144 | bs4-team-144-{01..04} | 6005-6008 | 192.168.144.{210..213} |
| vmbr145 | bs4-team-145-{01..04} | 6009-6012 | 192.168.145.{210..213} |
| vmbr146 | bs4-team-146-{01..04} | 6013-6016 | 192.168.146.{210..213} |

## Admin VMs (optional, commented out)

| VM | VM ID | IP | Bridge |
|----|-------|----|--------|
| admin-wazuh | 6100 | 192.168.142.100 | vmbr142 |
| admin-deployer-api-gateway | 6101 | 192.168.142.120 | vmbr142 |
| admin-deployer-api-backend | 6102 | 192.168.142.121 | vmbr142 |
| admin-deployer-ui | 6103 | 192.168.142.123 | vmbr142 |

## Stages

- **stage_00** — VM creation (clone template + cloud-init + start)
- **stage_01** — Basic packages, dotfiles, firewall (SSH only)

## Scripts

| Script | What it does |
|--------|-------------|
| `blank_scenario_4_subnets.setup.sh` | Full deploy (templates + VMs + software) |
| `blank_scenario_4_subnets.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `blank_scenario_4_subnets.delete_all.sh` | Destroy everything + clean SSH known_hosts |
| `blank_scenario_4_subnets.delete_vms_only.sh` | Destroy VMs only (keep templates) |
| `blank_scenario_4_subnets.reset.setup.sh` | Delete all + redeploy from scratch |
