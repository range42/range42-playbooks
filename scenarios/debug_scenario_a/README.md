# debug_scenario_a

Minimal debug/dev scenario — 1 VM on 1 subnet. Designed for fast iteration.

## Network architecture

```
                              ┌───────────────────────┐
                              │     Proxmox Host      │
                              └──────────┬────────────┘
                                         │
                                      vmbr147
                                    (debug A)
                                         │
                              ┌──────────┴────────────┐
                              │ 192.168.147.0/24      │
                              │                       │
                              │ dsa-vm-01       .250  │
                              └───────────────────────┘
```

## VM details

| VM Name | VM ID | IP | Bridge | Template |
|---------|-------|-------|--------|----------|
| dsa-vm-01 | 8001 | 192.168.147.250 | vmbr147 | template-vm-alpine-nano (9903) |

## Usage

```bash
range42-context use <codename> debug_scenario_a
range42-context deploy
```
