# blank_scenario_6_subnets

Minimal network lab — 6 team subnets, 4 VMs each (24 VMs). Optional admin subnet with wazuh + deployer platform.

> **DEPLOY_ADMIN_INFRASTRUCTURE: NO** (default) — admin VMs are commented out. Uncomment in `main.yml` and `01_admin_infrastructure/_main.yml` to deploy.

## Network architecture

```
                                               ┌───────────────────────────┐
                                               │       Proxmox Host        │
                                               │      (ip_forward=1)       │
                                               └┬─────┬─────┬─────┬─────┬─────┬─────┬┘
                                                │     │     │     │     │     │     │
                                          vmbr142  143  144  145  146  147  vmbr148
                                          (admin)  ←─── team subnets ───→
                                                │     │     │     │     │     │     │
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Admin (opt.) │ │ Team A       │ │ Team B       │ │ Team C       │ │ Team D       │ │ Team E       │ │ Team F       │
│ 142.0/24     │ │ 143.0/24     │ │ 144.0/24     │ │ 145.0/24     │ │ 146.0/24     │ │ 147.0/24     │ │ 148.0/24     │
│              │ │              │ │              │ │              │ │              │ │              │ │              │
│ wazuh  .100  │ │ -01    .220  │ │ -01    .220  │ │ -01    .220  │ │ -01    .220  │ │ -01    .220  │ │ -01    .220  │
│ api-gw .120  │ │ -02    .221  │ │ -02    .221  │ │ -02    .221  │ │ -02    .221  │ │ -02    .221  │ │ -02    .221  │
│ api-b  .121  │ │ -03    .222  │ │ -03    .222  │ │ -03    .222  │ │ -03    .222  │ │ -03    .222  │ │ -03    .222  │
│ ui     .123  │ │ -04    .223  │ │ -04    .223  │ │ -04    .223  │ │ -04    .223  │ │ -04    .223  │ │ -04    .223  │
│ (commented)  │ │              │ │              │ │              │ │              │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

## Team VMs (24 total)

| Subnet | VMs | VM IDs | IPs |
|--------|-----|--------|-----|
| vmbr143 | bs6-team-143-{01..04} | 7001-7004 | 192.168.143.{220..223} |
| vmbr144 | bs6-team-144-{01..04} | 7005-7008 | 192.168.144.{220..223} |
| vmbr145 | bs6-team-145-{01..04} | 7009-7012 | 192.168.145.{220..223} |
| vmbr146 | bs6-team-146-{01..04} | 7013-7016 | 192.168.146.{220..223} |
| vmbr147 | bs6-team-147-{01..04} | 7017-7020 | 192.168.147.{220..223} |
| vmbr148 | bs6-team-148-{01..04} | 7021-7024 | 192.168.148.{220..223} |

## Admin VMs (optional, commented out)

| VM | VM ID | IP | Bridge |
|----|-------|----|--------|
| admin-wazuh | 7100 | 192.168.142.100 | vmbr142 |
| admin-deployer-api-gateway | 7101 | 192.168.142.120 | vmbr142 |
| admin-deployer-api-backend | 7102 | 192.168.142.121 | vmbr142 |
| admin-deployer-ui | 7103 | 192.168.142.123 | vmbr142 |

## Stages

- **stage_00** — VM creation (clone template + cloud-init + start)
- **stage_01** — Basic packages, dotfiles, firewall (SSH only)

## Scripts

| Script | What it does |
|--------|-------------|
| `blank_scenario_6_subnets.setup.sh` | Full deploy (templates + VMs + software) |
| `blank_scenario_6_subnets.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `blank_scenario_6_subnets.delete_all.sh` | Destroy everything + clean SSH known_hosts |
| `blank_scenario_6_subnets.delete_vms_only.sh` | Destroy VMs only (keep templates) |
| `blank_scenario_6_subnets.reset.setup.sh` | Delete all + redeploy from scratch |
