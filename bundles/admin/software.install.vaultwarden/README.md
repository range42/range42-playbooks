# bundles/admin/software.install.vaultwarden

Self-hosted Vaultwarden credential store install bundle - 3 plays :

1. install Docker + docker-compose on the Vaultwarden VM (via `software.install.warmup.basic_packages` role)
2. open firewall ports 22 + the service port (default 8080) on the VM (via `software.configure.firewalls` role)
3. render the secret `.env` from the vault, optionally generate a self-signed TLS cert, and deploy the stack (via `software.configure.docker-compose` role : rsync catalog -> VM + `docker compose up -d`)

The catalog source is `range42-catalog/03_container_layer/docker/admin/vaultwarden/`
(one service : `vaultwarden/server`, pinned - see the element README).

> Note vs `software.install.nextcloud` / `software.install.misp_standalone` :
> those bundles seed the catalog's `.env.example` -> `.env`. This one does
> **not**. Vaultwarden refuses to start without `VW_ADMIN_TOKEN`, and that
> token must never live in git - so the `.env` is **rendered on the VM from
> vault-supplied vars** (`0600`, `no_log`). The catalog ships only
> `.env.example` and the rsync never overwrites the rendered file.

Companion bundle : [`admin/credentials.sync.vaultwarden`](../credentials.sync.vaultwarden/)
pushes/pulls credentials once the server is up.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-vaultwarden-standalone` | inventory hostname of the Vaultwarden VM (play target) |
| `global_vm_ci_ip` | `192.168.142.189` | IP of the server (informational) |
| `OPERATOR_USER` | `alice` | unix user owning the deploy dir |
| `vaultwarden_domain` | `https://192.168.142.189:8080` | public URL clients use (written as `VW_DOMAIN`) |
| `vaultwarden_admin_token` | `{{ vault_vw_admin_token }}` | argon2 admin-token hash, **from the vault** |

## Optional vars

| var | default | purpose |
|-----|---------|---------|
| `vaultwarden_http_port` | `8080` | service port (also the firewall port opened) |
| `vaultwarden_tls` | `false` | serve HTTPS with a self-signed cert on the same port |
| `vaultwarden_tls_ip` | host part of `vaultwarden_domain` | SAN IP for that cert |
| `vaultwarden_ca_fetch_path` | `<workspace>/secrets/vaultwarden-cert.pem` | where `cert.pem` lands on the control node |
| `vaultwarden_signups_allowed` | `false` | self-registration (on briefly for bootstrap only) |
| `vaultwarden_invitations_allowed` | `true` | |
| `vaultwarden_org_creation_users` | `all` | |
| `vw_remote_project_dir` | `/home/<OPERATOR_USER>/vaultwarden` | deploy dir on the VM |
| `vw_vault_file` | `<workspace>/secrets/default_vault.yml` | override the autoloaded vault |

## Vault variables

Put the admin token in the scenario's `secrets/default_vault.yml` (never plaintext) :

```yaml
vault_vw_admin_token: "$argon2id$v=19$m=..."   # from the element's `make hash`
```

The sync bundle needs the rest (`vault_vw_client_id`, `vault_vw_client_secret`,
`vault_vw_master_password`, and optionally `vault_vw_org_id` /
`vault_vw_collection_id`).

## TLS

Two independent client requirements force HTTPS even inside a lab : the web
vault only logs in from a secure context (browser WebCrypto), and recent `bw`
CLIs refuse plain-HTTP servers. `vaultwarden_tls: true` handles it end to end :

- self-signed cert generated **on the target**, root-owned (the hardened
  container drops ALL capabilities and cannot read operator-owned keys) ;
- SAN covers the service IP **plus `127.0.0.1` / `localhost`**, so operators on
  jump-only routing can tunnel and override
  `-e vaultwarden_url=https://127.0.0.1:<local port>` ;
- `cert.pem` is fetched to `<workspace>/secrets/vaultwarden-cert.pem` ; pass
  that path to the sync bundle as `vaultwarden_ca_cert`.

## One-time account bootstrap

The service account and its personal API key are **not** created by this bundle
(Vaultwarden has no unattended account-creation path). Register the account
once via the web vault with signups briefly enabled, then turn signups back
off - see the catalog element README and the `vaultwarden_lab` scenario README
for the exact steps.

## Example call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.vaultwarden/main.yml"
  when: INSTALL_VAULTWARDEN | default("NO") | upper == "YES"
  vars:
    global_vm_ssh_name:      "r42.admin-vaultwarden-standalone"
    global_vm_ci_ip:         "192.168.142.189"
    OPERATOR_USER:           "alice"
    vaultwarden_domain:      "https://192.168.142.189:8080"
    vaultwarden_tls:         true
    vaultwarden_admin_token: "{{ vault_vw_admin_token }}"
    vaultwarden_http_port:   8080
```
