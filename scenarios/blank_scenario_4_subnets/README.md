# blank_scenario_4_subnets

Network lab — 4 team subnets (4 VMs each) + admin subnet (wazuh + deployer platform). Total: 20 VMs.

> Admin subnet uses **decaled IPs** `.130-.133` on `192.168.142.0/24` (vs bs2's `.100/.120-.123`
> and bs6's `.140-.143`) so this scenario can be deployed **in parallel with bs2 and bs6**
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
range42-context use <codename> blank_scenario_4_subnets
range42-context deploy
```

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
│ Admin              │ │ Team A             │ │ Team B             │ │ Team C             │ │ Team D             │
│ 192.168.142.0/24   │ │ 192.168.143.0/24   │ │ 192.168.144.0/24   │ │ 192.168.145.0/24   │ │ 192.168.146.0/24   │
│                    │ │                    │ │                    │ │                    │ │                    │
│ wazuh        .130  │ │ team-143-01  .210  │ │ team-144-01  .210  │ │ team-145-01  .210  │ │ team-146-01  .210  │
│ api-gw       .131  │ │ team-143-02  .211  │ │ team-144-02  .211  │ │ team-145-02  .211  │ │ team-146-02  .211  │
│ api-back     .132  │ │ team-143-03  .212  │ │ team-144-03  .212  │ │ team-145-03  .212  │ │ team-146-03  .212  │
│ deployer-ui  .133  │ │ team-143-04  .213  │ │ team-144-04  .213  │ │ team-145-04  .213  │ │ team-146-04  .213  │
└────────────────────┘ └────────────────────┘ └────────────────────┘ └────────────────────┘ └────────────────────┘
```

## Team VMs (16 total)

| Subnet | VMs | VM IDs | IPs |
|--------|-----|--------|-----|
| vmbr143 | bs4-team-143-{01..04} | 6001-6004 | 192.168.143.{210..213} |
| vmbr144 | bs4-team-144-{01..04} | 6005-6008 | 192.168.144.{210..213} |
| vmbr145 | bs4-team-145-{01..04} | 6009-6012 | 192.168.145.{210..213} |
| vmbr146 | bs4-team-146-{01..04} | 6013-6016 | 192.168.146.{210..213} |

## Admin VMs

| VM | VM ID | IP | Bridge |
|----|-------|----|--------|
| bs4-admin-wazuh | 6100 | 192.168.142.130 | vmbr142 |
| bs4-admin-deployer-api-gateway | 6101 | 192.168.142.131 | vmbr142 |
| bs4-admin-deployer-api-backend | 6102 | 192.168.142.132 | vmbr142 |
| bs4-admin-deployer-ui | 6103 | 192.168.142.133 | vmbr142 |

Source of truth for VM IDs/IPs/bridges : [`manifest/scenario_vms.json`](manifest/scenario_vms.json).

## Stages

- **stage_00** — VM creation (clone template + cloud-init + start)
- **stage_01** — Per-VM software install :
  - team VMs   : basic packages, dotfiles, firewall (SSH only)
  - admin VMs  : wazuh-indexer/server/dashboard install + deployer api-gateway/api-backend/ui

## Scripts

| Script | What it does |
|--------|-------------|
| `blank_scenario_4_subnets.setup.sh` | Full deploy (templates + VMs + software) |
| `blank_scenario_4_subnets.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `blank_scenario_4_subnets.delete_all.sh` | Destroy everything (VMs + templates) + clean SSH known_hosts |
| `blank_scenario_4_subnets.delete_vms_only.sh` | Destroy VMs only (keep templates) |
| `blank_scenario_4_subnets.reset.setup.sh` | Delete all + redeploy from scratch |

`range42-context` exposes the same operations plus VM lifecycle (`start`/`stop`/`pause`/`resume`),
`snapshot`/`revert`, and `delete-everything` (cross-scenario cleanup). See `range42-context --help`.
