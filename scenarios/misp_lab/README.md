# misp_lab

Single-VM scenario that delivers an Ubuntu LTS host pre-provisioned with the Docker baseline, ready to host MISP via docker-compose.

The VM (`admin-misp-standalone`, VMID 1180, IP `192.168.142.180` on `vmbr142`) is cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk). Once provisioned, the operator deploys the MISP docker-compose stack on top - that step is intentionally NOT part of this scenario (see Scope below).

## Scope

**In scope :**
- One Ubuntu LTS VM on vmbr142
- Docker engine + Docker Compose plugin
- zsh + vim dotfiles
- Basic utilities : curl, git, jq, vim, network diagnostic tools
- UFW firewall enabled with port 22 open
- NTP time sync

**Out of scope (deployed in a follow-up step) :**
- MISP itself (docker-compose stack)
- MISP modules
- MISP integrations (Vulnerability-Lookup, OpenCTI, etc.)
- TLS certificates / reverse proxy for the MISP web UI

MISP can be brought up in any of these ways once misp_lab is deployed :
- Apply a `range42-catalog` docker element targetting the misp_lab VM
- SSH into `r42.admin-misp-standalone` and `docker compose up` against an upstream misp-docker repo
- Add a `misp_lab.deploy_misp.yml` follow-up playbook (not yet present)

## Network architecture

```
         Proxmox Host
              |
              +-- vmbr142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- admin-misp-standalone (.180)  ............  VMID 1180
```

No dedicated subnet. The VM lives on `vmbr142`, the shared services bridge. The `.180` slot is reserved by misp_lab.

## VM details

| VM Name                | VM ID | IP                | Bridge   | Template                              |
|------------------------|-------|-------------------|----------|---------------------------------------|
| admin-misp-standalone  | 1180  | 192.168.142.180   | vmbr142  | template-vm-medium-02-8g-64g (9232)   |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1180 -> .180).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, and to audit for collisions, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## Usage

Activate the workspace and run the setup script :

```
range42-context use <codename> misp_lab
./misp_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + VM
range42-context deploy-vms        # VM only (template assumed present)
range42-context delete-vms        # destroys the VM, keeps the template
range42-context delete            # same as delete-vms here (template 9232 is shared, never owned by misp_lab)
```

## Stages

| Stage | Purpose |
|---|---|
| `01_init_proxmox/` | Download Ubuntu noble cloud-init image + create template 9232 (`template-vm-medium-02-8g-64g`). Idempotent : skips if already present from another scenario. |
| `02_misp_lab_infrastructure/stage_00/misp_lab_vm.yml` | VM clone from template 9232 + cloud-init + start + wait-for-SSH. |
| `02_misp_lab_infrastructure/stage_01/_r42_misp_lab_group.yml` | Docker baseline + zsh dotfiles + firewall (port 22 only). |

## Entry points

| Script | Purpose |
|---|---|
| `misp_lab.setup.sh` | Full provisioning (template + VM). Idempotent on the template stage. |
| `misp_lab.setup_vms_only.sh` | Skips template creation. Faster on repeat runs assuming template 9232 is already present. |
| `misp_lab.delete_vms_only.sh` | Destroys the misp_lab VM, preserves the template. |
| `misp_lab.delete_all.sh` | Alias of `delete_vms_only.sh` (template 9232 is shared across scenarios, never owned by misp_lab). |
| `misp_lab.reset.setup.sh` | Convenience : delete VM + redeploy in one shot. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> misp_lab`.

## Files

```
misp_lab/
  main.yml                          full deploy entrypoint
  main_vms_only.yml                 fast redeploy (skip templates)
  manifest/scenario_vms.json        source of truth for VMID / IP / bridge
  README.md
  misp_lab.setup.sh                 full deploy wrapper
  misp_lab.setup_vms_only.sh        fast redeploy wrapper
  misp_lab.delete_vms_only.sh       VM teardown
  misp_lab.delete_all.sh            alias
  misp_lab.reset.setup.sh           teardown + deploy
  01_init_proxmox/                  Ubuntu noble cloud-init image + template 9232
  02_misp_lab_infrastructure/       single-VM stages 00 + 01
  templates/                        scenario-level templates (inventory, vars, ssh-config, vault example)
```

