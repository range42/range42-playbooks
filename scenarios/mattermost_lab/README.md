# mattermost_lab

Single-VM scenario that deploys a **Mattermost** team-collaboration server (docker-compose stack) on a dedicated Ubuntu LTS host.

The VM (`admin-mattermost-standalone`, VMID 1182, IP `192.168.142.182` on `vmbr142`) is cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk), gets the Docker baseline, and runs the Mattermost stack from `range42-catalog/03_container_layer/docker/admin/mattermost/` via the shared bundle `bundles/admin/software.install.mattermost/`.

Mattermost is modeled as an **admin-tier service** gated by `INSTALL_MATTERMOST`. In `mattermost_lab` the flag **defaults YES** (this is the Mattermost showcase scenario). The same bundle + wrapper is reused by the general scenarios as an optional add-on, where the flag defaults NO.

## Scope

**In scope :**
- One Ubuntu LTS VM on vmbr142
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

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

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
