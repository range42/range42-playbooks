# vaultwarden_lab

Single-VM scenario that deploys a **self-hosted Vaultwarden** credential store (an API-compatible Bitwarden server, one docker-compose service) on a dedicated Ubuntu LTS host, and demonstrates **credential distribution** : pushing secrets from the scenario's Ansible vault into Vaultwarden and pulling them back.

The VM (`admin-vaultwarden-standalone`, VMID 1189, IP `192.168.142.189` on `vmbr142`) is cloned from the project standard medium Ubuntu noble template (VMID 9232 - 2cpu / 8gb RAM / 64gb disk), gets the Docker baseline, and runs the Vaultwarden element from `range42-catalog/03_container_layer/docker/admin/vaultwarden/` via the shared bundle `bundles/admin/software.install.vaultwarden/`.

Vaultwarden is modeled as an **admin-tier service** gated by `INSTALL_VAULTWARDEN`. In `vaultwarden_lab` the flag **defaults YES** (this is the Vaultwarden showcase scenario). The same bundle + wrapper is reused by the general scenarios as an optional add-on, where the flag defaults NO.

The credential **get/set round-trip** is a second, separate flag (`INSTALL_VAULTWARDEN_SYNC`, default **NO**) driving `bundles/admin/credentials.sync.vaultwarden/` from the control node - it needs local tooling and a one-time account bootstrap, both described below.

## Scope

**In scope :**
- One Ubuntu LTS VM on vmbr142
- Docker engine + Docker Compose plugin
- zsh + vim dotfiles, basic utilities, NTP
- UFW firewall : ports 22 (SSH) + 8080 (Vaultwarden) - 8080 opened by the bundle
- Vaultwarden server deployed with a secret `.env` rendered from the vault, served over **self-signed HTTPS**

**Optional (off by default) :**
- Credential sync round-trip (`INSTALL_VAULTWARDEN_SYNC`, default NO)
- Tailscale VPN client (`INSTALL_TAILSCALE`, default NO)

## Network architecture

```
         Proxmox Host
              |
              +-- vmbr142 (shared services bridge - 192.168.142.0/24, gw .1)
                     |
                     +-- admin-vaultwarden-standalone (.189)  ............  VMID 1189
```

No dedicated subnet. The VM lives on `vmbr142`, the shared services bridge. The `.189` slot is reserved by vaultwarden_lab.

## VM details

| VM Name                        | VM ID | IP                | Bridge   | Template                              |
|--------------------------------|-------|-------------------|----------|---------------------------------------|
| admin-vaultwarden-standalone   | 1189  | 192.168.142.189   | vmbr142  | template-vm-medium-02-8g-64g (9232)   |

Source of truth : `manifest/scenario_vms.json`.

Project convention : last 3 digits of VMID match the IP last octet (1189 -> .189).

For the project-wide view of which VMIDs and IPs are reserved across all scenarios, see `scenarios/_reserved.json` and run `scenarios/_check_reserved.sh`.

## Usage

```
range42-context use <codename> vaultwarden_lab
./vaultwarden_lab.setup.sh
```

Or drive directly via `range42-context` :

```
range42-context deploy            # full setup : template (if missing) + VM + Vaultwarden
range42-context deploy-vms        # VM + Vaultwarden only (template assumed present)
range42-context delete-vms        # destroys the VM, keeps the template
```

To deploy the VM without Vaultwarden (bare Docker host) : `-e INSTALL_VAULTWARDEN=NO`.

## ⚠ Required before deploying : the admin token

Vaultwarden **refuses to start** without `VW_ADMIN_TOKEN`, so `vault_vw_admin_token`
must be in the workspace vault before the first deploy. Generate the argon2 hash
from the catalog element :

```
cd $RANGE42_INVENTORY/03_container_layer/docker/admin/vaultwarden
make hash          # prompts for a token, prints an $argon2id$... string
```

Then set it in the vault **single-quoted** (it contains `$` segments) - see
`templates/vault-example.yml`. Unlike the other admin stacks, the `.env` is not
seeded from the catalog's `.env.example` : the bundle renders it on the VM from
the vault (`0600`, `no_log`) so the token never lands in git.

## Vaultwarden credential sync (opt-in)

The round-trip pushes `vw_demo_secret` from the vault into a
`range42-<codename>-poc` item, then pulls it straight back into the fact
`vw_demo_pulled`. Run it standalone once the prerequisites below are met :

```
./vaultwarden_lab.poc.sh
```

**Control-node prerequisites :** the Bitwarden CLI (`bw`) and `jq` must be installed on the machine running the playbook - the `credentials.vaultwarden` role drives `bw` locally to reach the self-hosted server. Current bw CLIs (2026.x) work here because the scenario serves TLS and the element pins `vaultwarden/server` >= 1.37.0 - see "Client compatibility" in the catalog element README for the matrix (older servers or plain HTTP need `bw` <= 2025.6.1).

**TLS :** the scenario serves self-signed HTTPS on the same port (`vaultwarden_tls: true` in `02_admin_infrastructure/stage_01-vm_configure/admin-vaultwarden.yml`). The deploy fetches the cert to `<workspace>/secrets/vaultwarden-cert.pem` and the sync trusts it automatically. Browsers : accept the warning once. **Jump-only routing** (control node cannot reach `192.168.142.189` directly) : open a tunnel through the jump host and override the URL - the cert's SAN includes `127.0.0.1` for exactly this :

```
ssh -f -N -L 18080:192.168.142.189:8080 px.<codename>.jumper
./vaultwarden_lab.poc.sh -e vaultwarden_url=https://127.0.0.1:18080
```

**One-time Vaultwarden bootstrap** (the account can only be created once the server is running - Vaultwarden has no unattended account-creation path) :

1. Deploy the host and the server first (`./vaultwarden_lab.setup.sh`, with `vault_vw_admin_token` set as above). Confirm it is serving :
   `curl -sk https://192.168.142.189:8080/alive` -> a UTC timestamp.
2. Temporarily enable signups : set `VW_SIGNUPS_ALLOWED=true` in the rendered `.env` on the VM and `make reload-env` (`.env` changes need a re-create ; a plain `make restart` does **not** reload it).
3. Register the service account via the web vault at `https://192.168.142.189:8080`, then set signups back to `false` and reload again.
4. In that account : create a personal API key (Account Settings > Security > Keys) and note `client_id` / `client_secret`. Fill `vault_vw_client_id`, `vault_vw_client_secret`, `vault_vw_master_password` and `vw_demo_secret` in the vault. Optionally set `vault_vw_org_id` / `vault_vw_collection_id` for org scoping.
5. Run `./vaultwarden_lab.poc.sh`. Both directions should now succeed - the pulled value equals the pushed one.

Before the bootstrap, the sync **fails loudly** with `bw login failed …` (no account yet). That failure is the designed behaviour, not a bug : this path distributes secrets, so it never falls back silently.

See `bundles/admin/credentials.sync.vaultwarden/README.md` and the catalog element README for the authoritative details.

## Structure (canonical bundle-driven)

| Path | Purpose |
|---|---|
| `01_templates-bootstrap/_main.yml` | Build template 9232 (`medium-02`) via the shared templates bundle. Idempotent. |
| `02_admin_infrastructure/_main_stage_00.yml` | VM bootstrap (clone 9232 + cloud-init + start + wait-for-SSH) via the `proxmox/vm.bootstrap` bundle, gated `INSTALL_VAULTWARDEN`. |
| `02_admin_infrastructure/_main_stage_01.yml` | Build `r42_admin_active` + baseline (Docker, dotfiles, firewall 22) + `admin-vaultwarden.yml` -> the install bundle (firewall 8080 + `.env` + TLS + compose up), then `admin-vaultwarden-sync.yml` -> the sync bundle (opt-in). |

## Entry points

| Script | Purpose |
|---|---|
| `vaultwarden_lab.setup.sh` | Full provisioning (template + VM + Vaultwarden). |
| `vaultwarden_lab.setup_vms_only.sh` | Skips template creation (template 9232 assumed present). |
| `vaultwarden_lab.poc.sh` | Opt-in credential sync round-trip (needs the bootstrap above). |
| `vaultwarden_lab.delete_vms_only.sh` | Destroys the VM, preserves the template. |
| `vaultwarden_lab.delete_all.sh` | VMs + template (⚠ template 9232 is shared across scenarios). |
| `vaultwarden_lab.reset.setup.sh` | Delete VM + redeploy in one shot. |
| `vaultwarden_lab.reset.ssh_keys.sh` | Clear known_hosts entries (by IP + r42.<name> alias) from the manifest. |

All scripts require `RANGE42_ANSIBLE_ROLES__INVENTORY_DIR` and `RANGE42_VAULT_PASSWORD_FILE` to be exported - set by `range42-context use <codename> vaultwarden_lab`.

## Accessing Vaultwarden

Web vault : `https://192.168.142.189:8080` (self-signed - accept the warning once ; the web vault needs a secure context to log in at all, which is why TLS is on by default here).

Admin panel : `https://192.168.142.189:8080/admin`, unlocked with the **plaintext** token whose argon2 hash is in `vault_vw_admin_token`.

Health check : `curl -sk https://192.168.142.189:8080/alive`.

Container state :

```
ssh r42.admin-vaultwarden-standalone
cd ~/vaultwarden && docker ps --filter name=vaultwarden
```
