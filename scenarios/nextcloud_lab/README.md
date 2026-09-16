# nextcloud_lab

Single-VM scenario that deploys a **Nextcloud** self-hosted file-sync / collaboration server (docker-compose stack) on a dedicated Ubuntu LTS host.

The VM (`admin-nextcloud-standalone`, VMID 1181, IP `192.168.142.181` on `net142`) is cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk), gets the Docker baseline, and runs the Nextcloud stack from `range42-catalog/03_container_layer/docker/admin/nextcloud/` via the shared bundle `bundles/admin/software.install.nextcloud/`.

Nextcloud is modeled as an **admin-tier service** gated by `INSTALL_NEXTCLOUD`. In `nextcloud_lab` the flag **defaults YES** (this is the Nextcloud showcase scenario). The same bundle + wrapper is reused by the general scenarios as an optional add-on, where the flag defaults NO.

## Read this before deploying

**Any legacy `vmbrXXX` bridge carrying the same `.1` as a vnet must go.** See [Migrating from the bridge-based scenarios](#migrating-from-the-bridge-based-scenarios) - this is not optional, and the failure it causes is silent.

## Scope

**In scope :**
- One Ubuntu LTS VM on net142
- Docker engine + Docker Compose plugin
- zsh + vim dotfiles, basic utilities, NTP
- UFW firewall : ports 22 (SSH) + 8443 (Nextcloud HTTPS) - 8443 opened by the bundle
- Nextcloud docker-compose stack (postgres + redis + nextcloud + provisioner) deployed + bootstrapped (users + app passwords via the provisioner sidecar)

**Optional (off by default) :**
- Tailscale VPN client (`INSTALL_TAILSCALE`, default NO)

## Network architecture

```
         Proxmox Host
              |
              +-- net142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- admin-nextcloud-standalone (.181)  ............  VMID 1181
```

No dedicated subnet. The VM lives on `net142`, the shared services bridge. The `.181` slot is reserved by nextcloud_lab.

## VM details

| VM Name                       | VM ID | IP                | Bridge   | Template                              |
|-------------------------------|-------|-------------------|----------|---------------------------------------|
| admin-nextcloud-standalone    | 1181  | 192.168.142.181   | net142  | template-vm-medium-02-8g-64g (9232)   |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1181 -> .181).

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
range42-context use <codename> nextcloud_lab
./nextcloud_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + VM + Nextcloud
range42-context deploy-vms        # VM + Nextcloud only (template assumed present)
range42-context delete-vms        # destroys the VM, keeps the template
```

To deploy the VM without Nextcloud (bare Docker host) : `-e INSTALL_NEXTCLOUD=NO`.

## ⚠ Edit the catalog .env before deploying (NC_DOMAIN gotcha)

Mirroring the upstream catalog README ("edit secrets before deploying"), populate
the catalog `.env` BEFORE the deploy. One edit is **required** for this VM to be
reachable :

The shipped `.env.example` sets `NC_DOMAIN=localhost 192.168.142.250`, which does
**NOT** include this VM's IP (`192.168.142.181`). Nextcloud's `trusted_domains`
check rejects access through any host not listed in `NC_DOMAIN`, so browsing to
`https://192.168.142.181:8443` would fail. Add this VM's IP to `NC_DOMAIN` first :

```
cd $RANGE42_INVENTORY/03_container_layer/docker/admin/nextcloud/
cp .env.example .env
$EDITOR .env       # set NC_DOMAIN to include 192.168.142.181, e.g.
                   #   NC_DOMAIN=localhost 192.168.142.181
                   # also set POSTGRES_PASSWORD, NC_ADMIN_USER/PASS, HTTP_PORT
```

The bundle does NOT auto-fix this for you - it is an operator decision (see the bundle README). First build also needs **outbound egress** : the provisioner image fetches `yq` / `jq` from GitHub during its Dockerfile build.

## Structure (canonical bundle-driven)

| Path | Purpose |
|---|---|
| `01_templates-bootstrap/_main.yml` | Build template 9232 (`medium-02`) via the shared templates bundle. Idempotent. |
| `02_admin_infrastructure/_main_stage_00.yml` | VM bootstrap (clone 9232 + cloud-init + start + wait-for-SSH) via the core vm.bootstrap bundle, gated INSTALL_NEXTCLOUD. |
| `02_admin_infrastructure/_main_stage_01.yml` | Build `r42_admin_active` + baseline (Docker, dotfiles, firewall 22) + `admin-nextcloud.yml` thin wrapper -> the nextcloud bundle (firewall 8443 + docker compose up). |
| `02_admin_infrastructure/stage_01-vm_configure/admin_nextcloud_standalone.devkit/` | install / snapshot / revert helpers for the VM. |

## Entry points

| Script | Purpose |
|---|---|
| `nextcloud_lab.setup.sh` | Full provisioning (template + VM + Nextcloud). |
| `nextcloud_lab.setup_vms_only.sh` | Skips template creation (template 9232 assumed present). |
| `nextcloud_lab.delete_vms_only.sh` | Destroys the VM, preserves the template. |
| `nextcloud_lab.delete_all.sh` | VMs + template (⚠ template 9232 is shared across scenarios). |
| `nextcloud_lab.reset.setup.sh` | Delete VM + redeploy in one shot. |
| `nextcloud_lab.reset.ssh_keys.sh` | Clear known_hosts entries (by IP + r42.<name> alias) from the manifest. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> nextcloud_lab`.

## Accessing Nextcloud

Web UI : `https://192.168.142.181:8443` (only if `NC_DOMAIN` includes `192.168.142.181` - see the gotcha above). The provisioner sidecar seeds the users declared in the catalog `provisioning/users.yml` and writes app passwords :

```
ssh r42.admin-nextcloud-standalone
sudo docker exec nextcloud-provisioner cat /tokens/tokens.txt
```

WebDAV : `https://192.168.142.181:8443/remote.php/dav/files/<USERNAME>/`

Customize credentials before deploy by populating the catalog `.env` (see the bundle README).
