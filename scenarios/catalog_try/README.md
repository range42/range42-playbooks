# catalog_try

Disposable single-VM scenario for fast catalog element validation.

## Purpose

Provides a throwaway Proxmox VM (`catalog-try-vm-docker`, VMID 1250, IP `192.168.142.250` on `vmbr142`) provisioned with the Docker baseline. The VM is the target of `range42-context catalog-try <path>` for iterating on individual `range42-catalog` elements without standing up a full scenario.

The VM is overwritten on each `catalog-try` invocation : `delete-vms` + `deploy-vms` + apply the element + smoke check.

## Structure

This scenario mirrors the `demo_lab` pattern :

- `01_init_proxmox/` - download Ubuntu noble cloud-init image + create template 9221 (`template-vm-small-01-4g-32g`). Idempotent : skips if already present.
- `02_catalog-try_infrastructure/stage_00/catalog_try_vm.yml` - VM clone from template 9221 + cloud-init + start + wait-for-SSH
- `02_catalog-try_infrastructure/stage_01/_r42_catalog_try_group.yml` - Docker baseline + zsh dotfiles + firewall
- `manifest/scenario_vms.json` - single VM allocation (vm_id 1250, ip 192.168.142.250, bridge vmbr142)
- `templates/` - scenario-specific templates (ansible-inventory.j2, ansible-vars.yml, ssh-config.j2, vault-example.yml)

## Self-contained

catalog_try creates its own template (VMID 9221, ubuntu noble, 1cpu/4gb/32gb) via `01_init_proxmox/`. No dependency on another scenario's setup. If the template already exists on the Proxmox (e.g. from a prior `demo_lab.setup.sh` run, which creates the same VMID 9221), the template creation tasks are skipped idempotently.

## Entry points

| script | purpose |
|---|---|
| `catalog_try.setup.sh` | full provisioning (template + VM) ; idempotent on the template stage |
| `catalog_try.setup_vms_only.sh` | skips template creation (faster on repeated runs ; assumes template present) |
| `catalog_try.delete_vms_only.sh` | destroys the disposable VM, preserves the template |
| `catalog_try.delete_all.sh` | alias of `delete_vms_only.sh` (no scenario-specific templates beyond 9221 which other scenarios may share) |
| `catalog_try.reset.setup.sh` | convenience : delete VM + redeploy in one shot |

## Usage

The scenario is invoked transparently by `range42-context catalog-try <path>`. Direct usage :

```
range42-context use <codename> catalog_try
range42-context deploy            # full setup : template (if missing) + VM
range42-context deploy-vms        # VM only (template assumed present)
range42-context catalog-try docker/_ctf/hello   # deploys + smoke-tests a catalog element
range42-context delete-vms        # destroys the VM
```
