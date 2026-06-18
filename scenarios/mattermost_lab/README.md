# mattermost_lab

Single-VM scenario that delivers an Ubuntu LTS host pre-provisioned with the Docker baseline, ready to host Mattermost via docker-compose.

The VM (`admin-mattermost-standalone`, VMID 1182, IP `192.168.142.182` on `vmbr142`) is cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk). Once provisioned, the operator deploys the Mattermost docker-compose stack on top - that step is intentionally NOT part of this scenario (see Scope below).

## Scope

**In scope :**
- One Ubuntu LTS VM on vmbr142
- Docker engine + Docker Compose plugin
- zsh + vim dotfiles
- Basic utilities : curl, git, jq, vim, network diagnostic tools
- UFW firewall enabled with port 22 open
- NTP time sync

**Out of scope (deployed in a follow-up step) :**
- Mattermost itself (docker-compose stack)
- Mattermost integrations and plugins
- TLS certificates / reverse proxy for the Mattermost web UI

Mattermost can be brought up in any of these ways once mattermost_lab is deployed :
- Apply a `range42-catalog` docker element targeting the mattermost_lab VM (`docker/admin/mattermost`)
- SSH into `r42.admin-mattermost-standalone` and `docker compose up` against the catalog stack
- Add a `mattermost_lab.deploy_mattermost.yml` follow-up playbook (not yet present)

## Network architecture

```
         Proxmox Host
              |
              +-- vmbr142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- admin-mattermost-standalone (.182)  ............  VMID 1182
```

No dedicated subnet. The VM lives on `vmbr142`, the shared services bridge. The `.182` slot is reserved by mattermost_lab.

## VM details

| VM Name                       | VM ID | IP                | Bridge   | Template                              |
|-------------------------------|-------|-------------------|----------|---------------------------------------|
| admin-mattermost-standalone   | 1182  | 192.168.142.182   | vmbr142  | template-vm-medium-02-8g-64g (9232)   |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1182 -> .182).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, and to audit for collisions, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## Usage

Activate the workspace and run the setup script :

```
range42-context use <codename> mattermost_lab
./mattermost_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + VM
range42-context deploy-vms        # VM only (template assumed present)
range42-context delete-vms        # destroys the VM, keeps the template
range42-context delete            # same as delete-vms here (template 9232 is shared, never owned by mattermost_lab)
```

## Stages

| Stage | Purpose |
|---|---|
| `01_init_proxmox/` | Download Ubuntu noble cloud-init image + create template 9232 (`template-vm-medium-02-8g-64g`). Idempotent : skips if already present from another scenario. |
| `02_mattermost_lab_infrastructure/stage_00/mattermost_lab_vm.yml` | VM clone from template 9232 + cloud-init + start + wait-for-SSH. |
| `02_mattermost_lab_infrastructure/stage_01/_r42_mattermost_lab_group.yml` | Docker baseline + zsh dotfiles + firewall (port 22 only). |

## Entry points

| Script | Purpose |
|---|---|
| `mattermost_lab.setup.sh` | Full provisioning (template + VM). Idempotent on the template stage. |
| `mattermost_lab.setup_vms_only.sh` | Skips template creation. Faster on repeat runs assuming template 9232 is already present. |
| `mattermost_lab.delete_vms_only.sh` | Destroys the mattermost_lab VM, preserves the template. |
| `mattermost_lab.delete_all.sh` | Alias of `delete_vms_only.sh` (template 9232 is shared across scenarios, never owned by mattermost_lab). |
| `mattermost_lab.reset.setup.sh` | Convenience : delete VM + redeploy in one shot. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> mattermost_lab`.

## Files

```
mattermost_lab/
  main.yml                              full deploy entrypoint
  main_vms_only.yml                     fast redeploy (skip templates)
  manifest/scenario_vms.json            source of truth for VMID / IP / bridge
  README.md
  mattermost_lab.setup.sh               full deploy wrapper
  mattermost_lab.setup_vms_only.sh      fast redeploy wrapper
  mattermost_lab.delete_vms_only.sh     VM teardown
  mattermost_lab.delete_all.sh          alias
  mattermost_lab.reset.setup.sh         teardown + deploy
  01_init_proxmox/                      Ubuntu noble cloud-init image + template 9232
  02_mattermost_lab_infrastructure/     single-VM stages 00 + 01
  templates/                            scenario-level templates (inventory, vars, ssh-config, vault example)
```
