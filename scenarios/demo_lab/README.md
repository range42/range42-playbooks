# demo_lab

Default scenario — deploys admin services (wazuh, deployer API/UI) and CTF vulnerable boxes.

> **Work in progress** — the deployer UI and backend API are not yet configured on their VMs.
> Docker registry, student infrastructure, and additional services will be added later.

## Network architecture

```
                            ┌───────────────────────────┐
                            │       Proxmox Host        │
                            │      (ip_forward=1)       │
                            └──┬───────┬───────┬─────┬──┘
                               │       │       │     │
                      vmbr140  │ vmbr142│ vmbr143 vmbr144
                   ┌───────────┘       │       │     └──────────────┐
                   │                   │       │                    │
    ┌──────────────┴──────────┐  ┌─────┴───────────────┐  ┌────────┴──────────────────┐
    │  Templates (ephemeral)  │  │  Admin               │  │  CTF / Vuln               │
    │  192.168.140.0/24       │  │  192.168.142.0/24    │  │  192.168.144.0/24         │
    │                         │  │                      │  │                           │
    │  clone source for       │  │  wazuh          .100 │  │  vuln-box-00        .170  │
    │  all VMs                │  │  api-gateway    .120 │  │  vuln-box-01        .171  │
    │                         │  │  api-backend    .121 │  │  vuln-box-02        .172  │
    │                         │  │  deployer-ui    .123 │  │  vuln-box-03        .173  │
    │                         │  │                      │  │  vuln-box-04        .174  │
    └─────────────────────────┘  └──────────────────────┘  └───────────────────────────┘

    Student bridge (vmbr143, 192.168.143.0/24) — disabled, not deployed
    Planned: student-box-01 (.160), more student boxes TBD
```

Wazuh agents on student/ctf bridges reach the wazuh server (192.168.142.100) through the Proxmox gateway.

## Deployed VMs

### 02_admin_infrastructure (vmbr142)

| VM | VM ID | IP |
|----|-------|----|
| admin-wazuh | 1000 | 192.168.142.100 |
| admin-deployer-api-gateway | 1020 | 192.168.142.120 |
| admin-deployer-api-backend | 1021 | 192.168.142.121 |
| admin-deployer-ui | 1023 | 192.168.142.123 |

### 04_ctf_infrastructure (vmbr144)

| VM | VM ID | IP |
|----|-------|----|
| vuln-box-00 | 4000 | 192.168.144.170 |
| vuln-box-01 | 4001 | 192.168.144.171 |
| vuln-box-02 | 4002 | 192.168.144.172 |
| vuln-box-03 | 4003 | 192.168.144.173 |
| vuln-box-04 | 4004 | 192.168.144.174 |

## Stages

Each infrastructure section follows staged deployment:

- **stage_00** — VM creation (clone template + cloud-init + start)
- **stage_01** — Software installation (Ansible roles from catalog)
- **stage_02** — Post-install configuration (optional)

## Scripts

| Script | What it does |
|--------|-------------|
| `demo_lab.setup.sh` | Full deploy (templates + VMs + software) |
| `demo_lab.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `demo_lab.delete_all.sh` | Destroy everything + clean SSH known_hosts |
| `demo_lab.delete_vms_only.sh` | Destroy VMs only (keep templates) |
| `demo_lab.reset.setup.sh` | Delete all + redeploy from scratch |
| `demo_lab.reset.ssh_keys.sh` | Reset SSH keys only |
