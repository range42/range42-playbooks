# gitea_registry_lab

Single-VM scenario that delivers an Ubuntu LTS host pre-provisioned with the Docker baseline, ready to host Gitea (with OCI container registry) via docker-compose.

The VM (`admin-gitea-registry-standalone`, VMID 1186, IP `192.168.142.186` on `net142`) is cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk). Once provisioned, the operator deploys the Gitea docker-compose stack on top - that step is intentionally NOT part of this scenario (see Scope below).

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## Scope

**In scope :**
- One Ubuntu LTS VM on net142
- Docker engine + Docker Compose plugin
- zsh + vim dotfiles
- Basic utilities : curl, git, jq, vim, network diagnostic tools
- UFW firewall enabled with port 22 open
- NTP time sync

**Out of scope (deployed in a follow-up step) :**
- Gitea itself (docker-compose stack with OCI packages enabled)
- Gitea apps and integrations
- TLS certificates / reverse proxy for the Gitea web UI

Gitea (with registry) can be brought up in any of these ways once gitea_registry_lab is deployed :
- Apply a `range42-catalog` docker element targeting the gitea_registry_lab VM
- SSH into `r42.admin-gitea-registry-standalone` and `docker compose up` against the catalog stack (`range42-catalog/03_container_layer/docker/admin/gitea-registry/`)
- Add a `gitea_registry_lab.deploy_gitea_registry.yml` follow-up playbook (not yet present)

## Network architecture

```
         Proxmox Host
              |
              +-- net142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- admin-gitea-registry-standalone (.186)  ........  VMID 1186
```

No dedicated subnet. The VM lives on `net142`, the shared services bridge. The `.186` slot is reserved by gitea_registry_lab.

## VM details

| VM Name                           | VM ID | IP                | Bridge   | Template                              |
|-----------------------------------|-------|-------------------|----------|---------------------------------------|
| admin-gitea-registry-standalone   | 1186  | 192.168.142.186   | net142  | template-vm-medium-02-8g-64g (9232)   |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1186 -> .186).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, and to audit for collisions, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the two vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the gitea-registry-lab tier |

The vnet name follows the third octet of its subnet: `net143` carries `192.168.143.0/24`. The zone is `simple`, which means it is host-local - the Proxmox holds the `.1` of every subnet and routes between them, and outbound internet comes from the SNAT rule, not from the physical network knowing these ranges exist.

**It creates, it never deletes.** Each object is looked up first and only what is missing is written, so a second run is a no-op and an existing object is left alone. A vnet name is global to the cluster: deleting one here would take away a network other scenarios attach to. The delete scripts of this scenario remove VMs only.

**The order is not a preference.** `net140` is the templating network and the template build runs `apt`. Without a live SNAT rule there, the templates come out empty and out of date - so a template tier that runs first produces broken templates.

## Migrating from the bridge-based scenarios

A `vmbrNNN` bridge and a `netNNN` vnet **cannot both carry the same `.1`**. If they do, the host resolves the route to the bridge, where no VM is attached, and ARPs into the void. Everything looks correct - the zone, the vnet, the subnet, the gateway and the SNAT rule are all there and stay there - but:

- SSH to the VM fails with `No route to host`, which reads like a timeout;
- the VM cannot reach the internet, because the NATed reply comes back and is lost the same way;
- cloud-init ends `degraded` after several minutes of network timeouts.

**No API check can see this.** The declaration is valid; the fault is in the host's routing table. The one command that tells you:

```bash
ip route get <the_vm_ip>      # must answer `dev netXXX`, not `dev vmbrXXX`
```

**So the switch to SDN is atomic per hypervisor.** Before deploying this scenario, the VMs of every bridge-based scenario using these ranges must be deleted and their `vmbrNNN` bridges freed. There is no gradual coexistence and no partial rollback.

While the bridge-creating tooling is still in place, `00_sdn_bootstrap/` imports the `proxmox/legacy_bridge.workaround.shadowed_subnet` bundle, which removes the duplicate address from the conflicting bridges - the address only, nothing written to disk, so `ifreload -a` puts it back. It refuses to run if a live VM is still attached to one of those bridges, rather than cutting that VM off mid-deployment. Skip it with `-e BUNDLE_LEGACY_SKIP=true` once the bridges are gone for good.

To clear those lines from the disk for good, so no `ifreload` can restore them, run `range42-context networks-legacy-clean` once - a migration step, not routine maintenance.

## Subnet isolation

**Not implemented yet.** Today the subnets reach each other: the host holds a gateway in each and routes between them. That is the expected state of this scenario, not a defect - a VM in `net143` can open a connection to a VM in `net144`.

Isolating them is a firewall matter, not a topology one: putting each vnet in its own zone would change nothing, because the host would still route. The work is in progress and will use per-NIC filtering with address sets, so that team subnets are isolated from each other while the deployer keeps reaching the VMs it manages - without that exception, no deployment could run at all.

## Usage

Activate the workspace and run the setup script :

```
range42-context use <codename> gitea_registry_lab
./gitea_registry_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + VM
range42-context deploy-vms        # VM only (template assumed present)
range42-context delete-vms        # destroys the VM, keeps the template
range42-context delete            # same as delete-vms here (template 9232 is shared, never owned by gitea_registry_lab)
```

## Stages

| Stage | Purpose |
|---|---|
| `01_init_proxmox/` | Download Ubuntu noble cloud-init image + create template 9232 (`template-vm-medium-02-8g-64g`). Idempotent : skips if already present from another scenario. |
| `02_gitea_registry_lab_infrastructure/stage_00/gitea_registry_lab_vm.yml` | VM clone from template 9232 + cloud-init + start + wait-for-SSH. |
| `02_gitea_registry_lab_infrastructure/stage_01/_r42_gitea_registry_lab_group.yml` | Docker baseline + zsh dotfiles + firewall (port 22 only). |

## Entry points

| Script | Purpose |
|---|---|
| `gitea_registry_lab.setup.sh` | Full provisioning (template + VM). Idempotent on the template stage. |
| `gitea_registry_lab.setup_vms_only.sh` | Skips template creation. Faster on repeat runs assuming template 9232 is already present. |
| `gitea_registry_lab.delete_vms_only.sh` | Destroys the gitea_registry_lab VM, preserves the template. |
| `gitea_registry_lab.delete_all.sh` | Destroys the VM + template 9232 (shared — see warning in script). |
| `gitea_registry_lab.reset.setup.sh` | Convenience : delete VM + redeploy in one shot. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> gitea_registry_lab`.

## Files

```
gitea_registry_lab/
  main.yml                                      full deploy entrypoint
  main_vms_only.yml                             fast redeploy (skip templates)
  manifest/scenario_vms.json                    source of truth for VMID / IP / bridge
  README.md
  gitea_registry_lab.setup.sh                   full deploy wrapper
  gitea_registry_lab.setup_vms_only.sh          fast redeploy wrapper
  gitea_registry_lab.delete_vms_only.sh         VM teardown
  gitea_registry_lab.delete_all.sh              VM + template teardown
  gitea_registry_lab.reset.setup.sh             teardown + deploy
  01_init_proxmox/                              Ubuntu noble cloud-init image + template 9232
  02_gitea_registry_lab_infrastructure/         single-VM stages 00 + 01
  templates/                                    scenario-level templates (inventory, vars, ssh-config, vault example)
```
