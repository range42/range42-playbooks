# demo_lab

Full cyber range lab with admin infrastructure, student workstations, and CTF vulnerable targets.

## Network segmentation

| Segment | Bridge | Subnet | Gateway |
|---------|--------|--------|---------|
| Templates (ephemeral) | vmbr140 | 192.168.140.0/24 | 192.168.140.1 |
| Admin infrastructure | vmbr142 | 192.168.142.0/24 | 192.168.142.1 |
| Student infrastructure | vmbr143 | 192.168.143.0/24 | 192.168.143.1 |
| CTF / vulnerable boxes | vmbr144 | 192.168.144.0/24 | 192.168.144.1 |

Inter-bridge routing works via Proxmox (ip_forward=1).
Wazuh agents on student/ctf bridges reach the wazuh server on 192.168.142.100 through the Proxmox gateway.

## Deployed VMs

### 02_admin_infrastructure (vmbr142)

| VM | VM ID | IP | Status |
|----|-------|----|--------|
| admin-wazuh | 1000 | 192.168.142.100 | active |
| admin-builder-docker-registry | 1001 | 192.168.142.101 | active |
| admin-builder-api-devkit | 1002 | 192.168.142.102 | active |
| admin-web-api-kong | 1020 | 192.168.142.120 | active |
| admin-web-builder-api | 1021 | 192.168.142.121 | active |
| admin-web-emp | 1022 | 192.168.142.122 | disabled |
| admin-web-deployer-ui | 1023 | 192.168.142.123 | disabled |
| testing-wazuh-client | 1111 | 192.168.142.111 | disabled |

### 03_student_infrastructure (vmbr143)

| VM | VM ID | IP | Status |
|----|-------|----|--------|
| student-box-01 | 3001 | 192.168.143.160 | active (commented in main.yml) |

### 04_ctf_infrastructure (vmbr144)

| VM | VM ID | IP | Status |
|----|-------|----|--------|
| vuln-box-00 | 4000 | 192.168.144.170 | active |
| vuln-box-01 | 4001 | 192.168.144.171 | active |
| vuln-box-02 | 4002 | 192.168.144.172 | active |
| vuln-box-03 | 4003 | 192.168.144.173 | active |
| vuln-box-04 | 4004 | 192.168.144.174 | active |

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
