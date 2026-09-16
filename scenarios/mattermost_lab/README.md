# mattermost_lab

Single-VM scenario that deploys a **Mattermost** team-collaboration server (docker-compose stack) on a dedicated Ubuntu LTS host.

The VM (`admin-mattermost-standalone`, VMID 1182, IP `192.168.142.182` on `net142`) is cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk), gets the Docker baseline, and runs the Mattermost stack from `range42-catalog/03_container_layer/docker/admin/mattermost/` via the shared bundle `bundles/admin/software.install.mattermost/`.

Mattermost is modeled as an **admin-tier service** gated by `INSTALL_MATTERMOST`. In `mattermost_lab` the flag **defaults YES** (this is the Mattermost showcase scenario). The same bundle + wrapper is reused by the general scenarios as an optional add-on, where the flag defaults NO.

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## Scope

**In scope :**
- One Ubuntu LTS VM on net142
- Docker engine + Docker Compose plugin
- zsh + vim dotfiles, basic utilities, NTP
- UFW firewall : ports 22 (SSH) + 8065 (Mattermost HTTP) - 8065 opened by the bundle
- Mattermost docker-compose stack (postgres + mattermost + provisioner) deployed + bootstrapped (users + access tokens via the provisioner sidecar)

**Optional (off by default) :**
- Tailscale VPN client (`INSTALL_TAILSCALE`, default NO)

## Network architecture

```
         Proxmox Host
              |
              +-- net142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- admin-mattermost-standalone (.182)  ............  VMID 1182
```

No dedicated subnet. The VM lives on `net142`, the shared services bridge. The `.182` slot is reserved by mattermost_lab.

## VM details

| VM Name                       | VM ID | IP                | Bridge   | Template                              |
|-------------------------------|-------|-------------------|----------|---------------------------------------|
| admin-mattermost-standalone   | 1182  | 192.168.142.182   | net142  | template-vm-medium-02-8g-64g (9232)   |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1182 -> .182).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## How the SDN networks are created

`00_sdn_bootstrap/` runs **before everything else** and brings up one zone holding the two vnets:

| vnet | subnet | gateway | SNAT | used by |
|---|---|---|---|---|
| `net140` | `192.168.140.0/24` | `.1` | yes | the template build |
| `net142` | `192.168.142.0/24` | `.1` | yes | the admin tier |

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

```
range42-context use <codename> mattermost_lab
./mattermost_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + VM + Mattermost
range42-context deploy-vms        # VM + Mattermost only (template assumed present)
range42-context delete-vms        # destroys the VM, keeps the template
```

To deploy the VM without Mattermost (bare Docker host) : `-e INSTALL_MATTERMOST=NO`.

## Structure (canonical bundle-driven)

| Path | Purpose |
|---|---|
| `01_templates-bootstrap/_main.yml` | Build template 9232 (`medium-02`) via the shared templates bundle. Idempotent. |
| `02_admin_infrastructure/_main_stage_00.yml` | VM bootstrap (clone 9232 + cloud-init + start + wait-for-SSH) via the core vm.bootstrap bundle, gated INSTALL_MATTERMOST. |
| `02_admin_infrastructure/_main_stage_01.yml` | Build `r42_admin_active` + baseline (Docker, dotfiles, firewall 22) + `admin-mattermost.yml` thin wrapper -> the mattermost bundle (firewall 8065 + docker compose up). |
| `02_admin_infrastructure/stage_01-vm_configure/admin_mattermost_standalone.devkit/` | install / snapshot / revert helpers for the VM. |

## Entry points

| Script | Purpose |
|---|---|
| `mattermost_lab.setup.sh` | Full provisioning (template + VM + Mattermost). |
| `mattermost_lab.setup_vms_only.sh` | Skips template creation (template 9232 assumed present). |
| `mattermost_lab.delete_vms_only.sh` | Destroys the VM, preserves the template. |
| `mattermost_lab.delete_all.sh` | VMs + template (⚠ template 9232 is shared across scenarios). |
| `mattermost_lab.reset.setup.sh` | Delete VM + redeploy in one shot. |
| `mattermost_lab.reset.ssh_keys.sh` | Clear known_hosts entries (by IP + r42.<name> alias) from the manifest. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> mattermost_lab`.

## Accessing Mattermost

Web UI : `http://192.168.142.182:8065`. The provisioner sidecar seeds the users declared in the catalog `provisioning/users.yml` and writes personal access tokens :

```
ssh r42.admin-mattermost-standalone
sudo docker exec mattermost-provisioner cat /tokens/tokens.txt
```

Customize credentials before deploy by populating the catalog `.env` (see the bundle README).
