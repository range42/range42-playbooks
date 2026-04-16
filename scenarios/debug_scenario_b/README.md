# debug_scenario_b

Minimal debug/dev scenario — 1 VM on 1 subnet. Designed for fast iteration.

## Network architecture

```
                              ┌───────────────────────┐
                              │     Proxmox Host      │
                              └──────────┬────────────┘
                                         │
                                      vmbr148
                                    (debug B)
                                         │
                              ┌──────────┴────────────┐
                              │ 192.168.148.0/24      │
                              │                       │
                              │ dsb-vm-01       .250  │
                              └───────────────────────┘
```

## VM details

| VM Name | VM ID | IP | Bridge | Template |
|---------|-------|-------|--------|----------|
| dsb-vm-01 | 8501 | 192.168.148.250 | vmbr148 | template-vm-alpine-nano (9903) |

## Usage

```bash
range42-context use <codename> debug_scenario_b
range42-context deploy
```
