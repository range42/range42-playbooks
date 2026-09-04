# rocketchat_lab

Single-VM scenario that deploys a **Rocket.Chat** team-collaboration server (docker-compose stack) on a dedicated Ubuntu LTS host.

The VM (`admin-rocketchat-standalone`, VMID 1185, IP `192.168.142.185` on `vmbr142`) is cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk), gets the Docker baseline, and runs the Rocket.Chat stack from `range42-catalog/03_container_layer/docker/admin/rocketchat/` via the shared bundle `bundles/admin/software.install.rocketchat/`.

Rocket.Chat is modeled as an **admin-tier service** gated by `INSTALL_ROCKETCHAT`. In `rocketchat_lab` the flag **defaults YES** (this is the Rocket.Chat showcase scenario). The same bundle + wrapper is reused by the general scenarios as an optional add-on, where the flag defaults NO.

## Scope

**In scope :**
- One Ubuntu LTS VM on vmbr142
- Docker engine + Docker Compose plugin
- zsh + vim dotfiles, basic utilities, NTP
- UFW firewall : ports 22 (SSH) + 3500 (Rocket.Chat HTTPS) - 3500 opened by the bundle
- Rocket.Chat docker-compose stack (mongodb + mongo-init-replica + rocketchat + provisioner) deployed + bootstrapped (users + access tokens via the provisioner sidecar)

**Optional (off by default) :**
- Tailscale VPN client (`INSTALL_TAILSCALE`, default NO)

## Network architecture

```
         Proxmox Host
              |
              +-- vmbr142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- admin-rocketchat-standalone (.185)  ............  VMID 1185
```

No dedicated subnet. The VM lives on `vmbr142`, the shared services bridge. The `.185` slot is reserved by rocketchat_lab.

## VM details

| VM Name                       | VM ID | IP                | Bridge   | Template                              |
|-------------------------------|-------|-------------------|----------|---------------------------------------|
| admin-rocketchat-standalone   | 1185  | 192.168.142.185   | vmbr142  | template-vm-medium-02-8g-64g (9232)   |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1185 -> .185).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## Usage

```
range42-context use <codename> rocketchat_lab
./rocketchat_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + VM + Rocket.Chat
range42-context deploy-vms        # VM + Rocket.Chat only (template assumed present)
range42-context delete-vms        # destroys the VM, keeps the template
```

To deploy the VM without Rocket.Chat (bare Docker host) : `-e INSTALL_ROCKETCHAT=NO`.

## Structure (canonical bundle-driven)

| Path | Purpose |
|---|---|
| `01_templates-bootstrap/_main.yml` | Build template 9232 (`medium-02`) via the shared templates bundle. Idempotent. |
| `02_admin_infrastructure/_main_stage_00.yml` | VM bootstrap (clone 9232 + cloud-init + start + wait-for-SSH) via the core vm.bootstrap bundle, gated INSTALL_ROCKETCHAT. |
| `02_admin_infrastructure/_main_stage_01.yml` | Build `r42_admin_active` + baseline (Docker, dotfiles, firewall 22) + `admin-rocketchat.yml` thin wrapper -> the rocketchat bundle (firewall 3500 + docker compose up). |
| `02_admin_infrastructure/stage_01-vm_configure/admin_rocketchat_standalone.devkit/` | install / snapshot / revert helpers for the VM. |

## Entry points

| Script | Purpose |
|---|---|
| `rocketchat_lab.setup.sh` | Full provisioning (template + VM + Rocket.Chat). |
| `rocketchat_lab.setup_vms_only.sh` | Skips template creation (template 9232 assumed present). |
| `rocketchat_lab.delete_vms_only.sh` | Destroys the VM, preserves the template. |
| `rocketchat_lab.delete_all.sh` | VMs + template (⚠ template 9232 is shared across scenarios). |
| `rocketchat_lab.reset.setup.sh` | Delete VM + redeploy in one shot. |
| `rocketchat_lab.reset.ssh_keys.sh` | Clear known_hosts entries (by IP + r42.<name> alias) from the manifest. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> rocketchat_lab`.

## First-boot timing

The stack uses a MongoDB replica-set ; cold-start convergence takes **~90-180 s**
on first deploy. The `mongo-init-replica` container initialises the `rs0` replica
set, then the `rocketchat` healthcheck must pass before the `provisioner` seeds
users + personal access tokens. `mongo-init-replica` and `provisioner` are
one-shot (`restart: "no"`). Re-runs are idempotent (replica set already
initialised, tokens already provisioned).

## Accessing Rocket.Chat

Web UI : `https://192.168.142.185:3500`. Default admin credentials : `rc-admin` / `Admin1234!` (change via the catalog `.env` before deploy). The provisioner sidecar seeds the users declared in the catalog `provisioning/users.yml` and writes personal access tokens :

```
ssh r42.admin-rocketchat-standalone
sudo docker exec rocketchat-provisioner cat /tokens/tokens.txt
```

Each token line has the format `username:personalAccessToken`. Customize credentials before deploy by populating the catalog `.env` (see the bundle README).
