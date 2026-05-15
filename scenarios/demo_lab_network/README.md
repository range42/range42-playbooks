# demo_lab_network

`demo_lab` + inter-bridge iptables isolation. Adds FORWARD chain firewall rules on the Proxmox host to enforce zone separation between the admin and CTF subnets.

> Closes #20

## What's new vs demo_lab

| | demo_lab | demo_lab_network |
|---|---|---|
| VM layout | identical | identical |
| Admin → CTF | allowed (default forward) | allowed (explicit ACCEPT) |
| CTF → Admin | allowed (default forward) | **DROPPED** |
| CTF → Internet | allowed (default forward) | **DROPPED** (air-gap) |
| CTF → Wazuh :1514/:1515 | allowed | **allowed** (explicit ACCEPT) |
| Proxmox iptables rules | none | `05_network_isolation` Ansible step |

## Network architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │              Proxmox Host (pve01)                │
                    │         ip_forward=1  •  iptables FORWARD        │
                    └───────────────────┬─────────────────┬────────────┘
                                        │                 │
                             ┌──────────┘                 └──────────┐
                             │  vmbr142                  vmbr144     │
                    ┌────────▼──────────────┐   ┌────────▼──────────────┐
                    │  Admin / Deployment   │   │  CTF / Vuln (air-gap) │
                    │  192.168.142.0/24     │   │  192.168.144.0/24     │
                    │                       │   │                       │
                    │  admin-wazuh    .100  │   │  vuln-box-00    .170  │
                    │  api-gateway    .120  │   │  vuln-box-01    .171  │
                    │  api-backend    .121  │   │  vuln-box-02    .172  │
                    │  deployer-ui    .123  │   │  vuln-box-03    .173  │
                    └───────────────────────┘   │  vuln-box-04    .174  │
                                                └───────────────────────┘
```

### iptables FORWARD rules (applied on Proxmox host)

| From | To | Port | Action | Reason |
|------|----|------|--------|--------|
| any | any | — | ACCEPT (ESTABLISHED,RELATED) | return traffic |
| Admin (.142/24) | CTF (.144/24) | ALL | ACCEPT | admin manages vuln boxes |
| CTF (.144/24) | Wazuh (.142.100) | 1514 TCP | ACCEPT | Wazuh agent events |
| CTF (.144/24) | Wazuh (.142.100) | 1515 TCP | ACCEPT | Wazuh agent enrollment |
| CTF (.144/24) | Admin (.142/24) | ALL | **DROP** | zone isolation |
| CTF (vmbr144) | WAN (vmbr0) | ALL | **DROP** | air-gap |

Rules are idempotent (`ansible.builtin.iptables` checks before inserting) and persist across reboots via `iptables-persistent`.

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

| Stage | What it does |
|-------|-------------|
| `01_init_proxmox` | Download cloud-init images, create Ubuntu Noble VM templates |
| `02_admin_infrastructure` | Create + configure admin VMs on vmbr142 |
| `04_ctf_infrastructure` | Create + configure CTF/vuln VMs on vmbr144 |
| `05_network_isolation` | Install `iptables-persistent` on pve01, apply FORWARD rules |

## Scripts

| Script | What it does |
|--------|-------------|
| `demo_lab_network.setup.sh` | Full deploy (templates + VMs + network isolation) |
| `demo_lab_network.setup_vms_only.sh` | Fast redeploy (VMs only, skip templates) |
| `demo_lab_network.delete_vms_only.sh` | Destroy VMs, keep templates |
| `demo_lab_network.delete_all.sh` | Destroy everything + clean SSH known_hosts |
| `demo_lab_network.reset.setup.sh` | Delete all + redeploy from scratch |
| `demo_lab_network.reset.ssh_keys.sh` | Reset SSH known_hosts entries only |

## Notes

- **VM IDs are the same as demo_lab** — do not run both scenarios on the same Proxmox simultaneously.
- The `05_network_isolation` step runs on the `proxmox` host (not on VMs). Requires SSH root access to pve01.
- If your Proxmox WAN interface is not `vmbr0`, override with `-e wan_interface=<iface>` or set `infrastructure_proxmox_default_network_card_interface` in group_vars.
- iptables rules are NOT removed by the delete scripts. Use `iptables -D FORWARD ...` manually if needed.

## Design notes

Two-zone design (admin/ctf) was chosen over a three-zone design with a dedicated management bridge because vmbr142/vmbr144 already pre-exist in the `proxmox.init` bridge configuration and Wazuh agent traffic is adequately handled via iptables pinholes on ports 1514/1515.

A three-zone design (with a dedicated `vmbr145` management bridge and dual NICs on vuln boxes) remains a valid future enhancement — it would eliminate the Wazuh iptables pinholes entirely and provide stronger monitoring isolation.
