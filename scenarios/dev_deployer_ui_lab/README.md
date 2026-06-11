# dev_deployer_ui_lab

Multi-VM scenario that delivers 3 Ubuntu LTS hosts pre-provisioned with the Docker baseline, ready to host the deployer-ui platform via docker-compose.

The 3 VMs (`dev-deployer-ui`, `dev-backend`, `dev-kong`) are cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk) onto the shared services bridge `vmbr142`. Once provisioned, the operator deploys the deployer-ui frontend, backend API, and Kong API gateway stacks on top - that step is intentionally NOT part of this scenario (see Scope below).

## Scope

**In scope :**
- 3 Ubuntu LTS VMs on vmbr142
- Docker engine + Docker Compose plugin on each VM
- zsh + vim dotfiles
- Basic utilities : curl, git, jq, vim, network diagnostic tools
- UFW firewall enabled with port 22 open
- NTP time sync

**Out of scope (deployed in a follow-up step) :**
- deployer-ui frontend (port 3000)
- backend API (port 8000)
- Kong API gateway (proxy 8000, admin 8001, proxy-ssl 8443, admin-ssl 8444)
- TLS certificates / reverse proxy in front of the stack
- Application-level firewall openings (kept closed at scenario time on purpose)

The deployer-ui stack can be brought up in any of these ways once dev_deployer_ui_lab is deployed :
- Apply a `range42-catalog` docker element targetting each VM
- SSH into `r42.dev-deployer-ui` / `r42.dev-backend` / `r42.dev-kong` and run `docker compose up` against the appropriate stack repo
- Add a `dev_deployer_ui_lab.deploy_stack.yml` follow-up playbook (not yet present)

Application ports stay closed by the scenario firewall ; opening them happens when the corresponding docker-compose stack is deployed.

## Network architecture

```
         Proxmox Host
              |
              +-- vmbr142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- dev-deployer-ui (.190)  ........  VMID 1190
                     +-- dev-backend     (.191)  ........  VMID 1191
                     +-- dev-kong        (.192)  ........  VMID 1192
```

No dedicated subnet. The 3 VMs live on `vmbr142`, the shared services bridge. The `.190`-`.192` slots are reserved by dev_deployer_ui_lab.

## VM details

| VM Name          | VM ID | IP                | Bridge   | Template                              | Hosts (follow-up step)        |
|------------------|-------|-------------------|----------|---------------------------------------|-------------------------------|
| dev-deployer-ui  | 1190  | 192.168.142.190   | vmbr142  | template-vm-medium-02-8g-64g (9232)   | deployer-ui frontend          |
| dev-backend      | 1191  | 192.168.142.191   | vmbr142  | template-vm-medium-02-8g-64g (9232)   | backend API                   |
| dev-kong         | 1192  | 192.168.142.192   | vmbr142  | template-vm-medium-02-8g-64g (9232)   | Kong API gateway              |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1190 -> .190, 1191 -> .191, 1192 -> .192).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, and to audit for collisions, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## Usage

Activate the workspace and run the setup script :

```
range42-context use <codename> dev_deployer_ui_lab
./dev_deployer_ui_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + 3 VMs
range42-context deploy-vms        # VMs only (template assumed present)
range42-context delete-vms        # destroys the 3 VMs, keeps the template
range42-context delete            # same as delete-vms here (template 9232 is shared, never owned by dev_deployer_ui_lab)
```

## Stages

| Stage | Purpose |
|---|---|
| `01_init_proxmox/` | Download Ubuntu noble cloud-init image + create template 9232 (`template-vm-medium-02-8g-64g`). Idempotent : skips if already present from another scenario. |
| `02_dev_deployer_ui_lab_infrastructure/stage_00/dev_deployer_ui_vm.yml` | VM clone from template 9232 + cloud-init + start + wait-for-SSH (dev-deployer-ui, 1190, .190). |
| `02_dev_deployer_ui_lab_infrastructure/stage_00/dev_backend_vm.yml`     | VM clone from template 9232 + cloud-init + start + wait-for-SSH (dev-backend, 1191, .191). |
| `02_dev_deployer_ui_lab_infrastructure/stage_00/dev_kong_vm.yml`        | VM clone from template 9232 + cloud-init + start + wait-for-SSH (dev-kong, 1192, .192). |
| `02_dev_deployer_ui_lab_infrastructure/stage_01/_r42_dev_deployer_ui_lab_group.yml` | Docker baseline + zsh dotfiles + firewall (port 22 only), fanned out over the 3 hosts in one pass. |

## Entry points

| Script | Purpose |
|---|---|
| `dev_deployer_ui_lab.setup.sh` | Full provisioning (template + 3 VMs). Idempotent on the template stage. |
| `dev_deployer_ui_lab.setup_vms_only.sh` | Skips template creation. Faster on repeat runs assuming template 9232 is already present. |
| `dev_deployer_ui_lab.delete_vms_only.sh` | Destroys the 3 dev_deployer_ui_lab VMs, preserves the template. |
| `dev_deployer_ui_lab.delete_all.sh` | Alias of `delete_vms_only.sh` (template 9232 is shared across scenarios, never owned by dev_deployer_ui_lab). |
| `dev_deployer_ui_lab.reset.setup.sh` | Convenience : delete the 3 VMs + redeploy in one shot. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> dev_deployer_ui_lab`.

## Files

```
dev_deployer_ui_lab/
  main.yml                                   full deploy entrypoint
  main_vms_only.yml                          fast redeploy (skip templates)
  manifest/scenario_vms.json                 source of truth for VMID / IP / bridge
  README.md
  dev_deployer_ui_lab.setup.sh               full deploy wrapper
  dev_deployer_ui_lab.setup_vms_only.sh      fast redeploy wrapper
  dev_deployer_ui_lab.delete_vms_only.sh     VM teardown
  dev_deployer_ui_lab.delete_all.sh          alias
  dev_deployer_ui_lab.reset.setup.sh         teardown + deploy
  01_init_proxmox/                           Ubuntu noble cloud-init image + template 9232
  02_dev_deployer_ui_lab_infrastructure/     3-VM stage_00 + stage_01
  templates/                                 scenario-level templates (inventory, vars, ssh-config, vault example)
```

