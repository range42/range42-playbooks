# blank_scenario_6_subnets

Network lab — 6 team subnets (4 VMs each) + admin subnet (wazuh + deployer platform). Total: 28 VMs.

> Admin subnet uses **decaled IPs** `.140-.143` on `192.168.142.0/24` (vs bs2's `.100/.120-.123`
> and bs4's `.130-.133`) so this scenario can be deployed **in parallel with bs2 and bs4**
> on the same Proxmox host without collision.

## How to deploy

On a fresh Linux machine that will become the operator's deployer-cli :

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3-venv git

mkdir -p $HOME/range42 && cd $HOME/range42
git clone https://github.com/range42/range42.git
cd range42
./range42-init.py
```

Follow the wizard prompts (Proxmox address, jump user, scenario, optional apt proxy).
Once the deployer-cli is configured, switch to the new context and deploy :

```bash
range42-context use <codename> blank_scenario_6_subnets
range42-context deploy
```

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
│ Admin        │ │ Team A       │ │ Team B       │ │ Team C       │ │ Team D       │ │ Team E       │ │ Team F       │
│ 142.0/24     │ │ 143.0/24     │ │ 144.0/24     │ │ 145.0/24     │ │ 146.0/24     │ │ 147.0/24     │ │ 148.0/24     │
│              │ │              │ │              │ │              │ │              │ │              │ │              │
│ wazuh  .140  │ │ -01    .220  │ │ -01    .220  │ │ -01    .220  │ │ -01    .220  │ │ -01    .220  │ │ -01    .220  │
│ api-gw .141  │ │ -02    .221  │ │ -02    .221  │ │ -02    .221  │ │ -02    .221  │ │ -02    .221  │ │ -02    .221  │
│ api-b  .142  │ │ -03    .222  │ │ -03    .222  │ │ -03    .222  │ │ -03    .222  │ │ -03    .222  │ │ -03    .222  │
│ ui     .143  │ │ -04    .223  │ │ -04    .223  │ │ -04    .223  │ │ -04    .223  │ │ -04    .223  │ │ -04    .223  │
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

## Admin VMs

| VM | VM ID | IP | Bridge |
|----|-------|----|--------|
| bs6-admin-wazuh | 7100 | 192.168.142.140 | vmbr142 |
| bs6-admin-deployer-api-gateway | 7101 | 192.168.142.141 | vmbr142 |
| bs6-admin-deployer-api-backend | 7102 | 192.168.142.142 | vmbr142 |
| bs6-admin-deployer-ui | 7103 | 192.168.142.143 | vmbr142 |

Source of truth for VM IDs/IPs/bridges : [`manifest/scenario_vms.json`](manifest/scenario_vms.json).

## Stages

- **stage_00** — VM creation (clone template + cloud-init + start)
- **stage_01** — Per-VM software install :
  - team VMs   : basic packages, dotfiles, firewall (SSH only)
  - admin VMs  : wazuh-indexer/server/dashboard install + deployer api-gateway/api-backend/ui

## Scripts

| Script | What it does |
|--------|-------------|
| `blank_scenario_6_subnets.setup.sh` | Full deploy (templates + VMs + software) |
| `blank_scenario_6_subnets.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `blank_scenario_6_subnets.delete_all.sh` | Destroy everything (VMs + templates) + clean SSH known_hosts |
| `blank_scenario_6_subnets.delete_vms_only.sh` | Destroy VMs only (keep templates) |
| `blank_scenario_6_subnets.reset.setup.sh` | Delete all + redeploy from scratch |

`range42-context` exposes the same operations plus VM lifecycle (`start`/`stop`/`pause`/`resume`),
`snapshot`/`revert`, and `delete-everything` (cross-scenario cleanup). See `range42-context --help`.
