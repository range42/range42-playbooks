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
    │  all VMs                │  │  api-gateway    .101 │  │  vuln-box-01        .171  │
    │                         │  │  api-backend    .102 │  │  vuln-box-02        .172  │
    │                         │  │  deployer-ui    .103 │  │  vuln-box-03        .173  │
    │                         │  │                      │  │  vuln-box-04        .174  │
    └─────────────────────────┘  └──────────────────────┘  └───────────────────────────┘

    Student bridge (vmbr143, 192.168.143.0/24) — reserved in manifest, not deployed by default
    Reserved : student-box-01 (vm_id 1160, IP .160). Import is commented out in `main.yml` ;
    uncomment `03_student_infrastructure/_main.yml` to enable. More student boxes TBD.
```

Wazuh agents on student/ctf bridges reach the wazuh server (192.168.142.100) through the Proxmox gateway.

## Deployed VMs

### 02_admin_infrastructure (vmbr142)

| VM | VM ID | IP |
|----|-------|----|
| admin-wazuh | 1100 | 192.168.142.100 |
| admin-deployer-api-gateway | 1101 | 192.168.142.101 |
| admin-deployer-api-backend | 1102 | 192.168.142.102 |
| admin-deployer-ui | 1103 | 192.168.142.103 |

### 04_ctf_infrastructure (vmbr144)

| VM | VM ID | IP |
|----|-------|----|
| vuln-box-00 | 1170 | 192.168.144.170 |
| vuln-box-01 | 1171 | 192.168.144.171 |
| vuln-box-02 | 1172 | 192.168.144.172 |
| vuln-box-03 | 1173 | 192.168.144.173 |
| vuln-box-04 | 1174 | 192.168.144.174 |

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

## Optional components - feature flags

The optional components shipped with this scenario can be toggled on/off at deploy
time. The catalog lives in [`manifest/feature_flags.yml`](manifest/feature_flags.yml) ;
the deploy scripts forward any trailing `-e INSTALL_<NAME>=<YES|NO>` to `ansible-playbook`
(same convention as the pre-existing `INSTALL_TAILSCALE` variable used elsewhere
in the scenario).

Example - deploy everything except wazuh, and force tailscale off on all groups :

```bash
range42-context deploy      -e INSTALL_WAZUH=NO
range42-context deploy-vms  -e INSTALL_WAZUH=NO -e INSTALL_TAILSCALE=NO
```

The same flags surface as checkboxes in `range42-context --tui` (deploy / deploy-vms entries).
