# blank_scenario_2_subnets

Minimal network lab — 2 team subnets (2 VMs each) + admin subnet (wazuh + deployer platform). Total: 8 VMs.

> Admin subnet uses the original layout `.100/.120/.121/.123` on `192.168.142.0/24`.
> bs4 and bs6 use **decaled** admin IPs (`.130-.133` and `.140-.143`) so all three
> scenarios can be deployed **in parallel** on the same Proxmox host without collision.

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
range42-context use <codename> blank_scenario_2_subnets
range42-context deploy
```

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
    │                          ┌────────────┘                                      │
    │                          │                                                   │
┌───┴──────────────────┐  ┌───┴──────────────────┐  ┌─────────────────────────────┴┐
│ Admin                │  │ Team A               │  │ Team B                       │
│ 192.168.142.0/24     │  │ 192.168.143.0/24     │  │ 192.168.144.0/24             │
│                      │  │                      │  │                              │
│ wazuh          .100  │  │ team-143-01    .200  │  │ team-144-01           .200   │
│ api-gateway    .120  │  │ team-143-02    .201  │  │ team-144-02           .201   │
│ api-backend    .121  │  │                      │  │                              │
│ deployer-ui    .123  │  │                      │  │                              │
└──────────────────────┘  └──────────────────────┘  └──────────────────────────────┘
```

## Team VMs

| VM | VM ID | IP | Bridge |
|----|-------|----|--------|
| bs2-team-143-01 | 5001 | 192.168.143.200 | vmbr143 |
| bs2-team-143-02 | 5002 | 192.168.143.201 | vmbr143 |
| bs2-team-144-01 | 5003 | 192.168.144.200 | vmbr144 |
| bs2-team-144-02 | 5004 | 192.168.144.201 | vmbr144 |

## Admin VMs

| VM | VM ID | IP | Bridge |
|----|-------|----|--------|
| bs2-admin-wazuh | 5100 | 192.168.142.100 | vmbr142 |
| bs2-admin-deployer-api-gateway | 5101 | 192.168.142.120 | vmbr142 |
| bs2-admin-deployer-api-backend | 5102 | 192.168.142.121 | vmbr142 |
| bs2-admin-deployer-ui | 5103 | 192.168.142.123 | vmbr142 |

Source of truth for VM IDs/IPs/bridges : [`manifest/scenario_vms.json`](manifest/scenario_vms.json).

## Stages

- **stage_00** — VM creation (clone template + cloud-init + start)
- **stage_01** — Per-VM software install :
  - team VMs   : basic packages, dotfiles, firewall (SSH only)
  - admin VMs  : wazuh-indexer/server/dashboard install + deployer api-gateway/api-backend/ui

## Scripts

| Script | What it does |
|--------|-------------|
| `blank_scenario_2_subnets.setup.sh` | Full deploy (templates + VMs + software) |
| `blank_scenario_2_subnets.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `blank_scenario_2_subnets.delete_all.sh` | Destroy everything (VMs + templates) + clean SSH known_hosts |
| `blank_scenario_2_subnets.delete_vms_only.sh` | Destroy VMs only (keep templates) |
| `blank_scenario_2_subnets.reset.setup.sh` | Delete all + redeploy from scratch |

`range42-context` exposes the same operations plus VM lifecycle (`start`/`stop`/`pause`/`resume`),
`snapshot`/`revert`, and `delete-everything` (cross-scenario cleanup). See `range42-context --help`.
