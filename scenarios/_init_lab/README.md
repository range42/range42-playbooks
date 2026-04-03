# _init_lab

Shared initialization scenario — creates VM templates and optional init VMs for testing.
Used as the base for other scenarios (demo_lab, forensics_lab, etc.).

## What it does

### 01_init_proxmox — VM templates

Creates cloud-init Ubuntu Noble templates on vmbr140.
These templates are cloned by other scenarios to create actual VMs.

| Template | VM ID | CPU | RAM | Bridge |
|----------|-------|-----|-----|--------|
| template-vm-nano | 9901 | 1 | 1G | vmbr140 |
| template-vm-micro-01 | 9211 | 1 | 2G | vmbr140 |
| template-vm-micro-02 | 9212 | 2 | 2G | vmbr140 |
| template-vm-small-01 | 9221 | 2 | 4G | vmbr140 |
| template-vm-small-02 | 9222 | 2 | 4G | vmbr140 |
| template-vm-small-04 | 9224 | 4 | 4G | vmbr140 |
| template-vm-medium-02 | 9232 | 2 | 8G | vmbr140 |
| template-vm-medium-04 | 9234 | 4 | 8G | vmbr140 |
| template-vm-medium-06 | 9236 | 6 | 8G | vmbr140 |
| template-vm-large-04 | 9244 | 4 | 8G | vmbr140 |
| template-vm-large-06 | 9246 | 6 | 8G | vmbr140 |
| template-vm-large-08 | 9248 | 8 | 8G | vmbr140 |

### 02_init_infrastructure — Init VMs (optional)

Creates temporary init VMs for testing template functionality.
These VMs are used to validate that cloud-init and networking work correctly
before deploying a full scenario.

## Scripts

| Script | What it does |
|--------|-------------|
| `init_lab.setup.sh` | Full deploy (download images + create templates) |
| `init_lab.delete_all.sh` | Destroy all templates and init VMs |
| `init_lab.reset.setup.sh` | Delete all + recreate |
| `init_lab.reset.ssh_keys.sh` | Reset SSH keys only |

## Relationship with other scenarios

```
_init_lab (templates on vmbr140)
    ↓ clone
demo_lab (VMs on vmbr142/143/144)
    ↓ clone (future)
forensics_lab, kunai_lab, misp_lab
```

Templates are created once, then cloned by each scenario.
The bridge is switched from vmbr140 to the target bridge during the clone
via `cloudinit_set_variables` (PUT net0).
