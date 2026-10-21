# bundles/admin/software.install.misp_standalone

MISP standalone docker-compose stack install bundle - 4 plays :

1. ensure catalog `.env` exists on localhost (cp `.env.example` -> `.env` if absent, force=false)
2. install Docker + docker-compose on the MISP VM (via `software.install.warmup.basic_packages` role)
3. open firewall ports 22 + 80 + 443 on the VM (via `software.configure.firewalls` role - the compose publishes 80 and 443, and the role default-denies incoming, so this play was missing)
4. stage the VM `.env` (seeded once from the catalog `.env`, `MISP_BASEURL=https://<global_vm_ci_ip>`, random `MISP_ADMIN_KEY` in place of the placeholder), then deploy the misp-standalone docker-compose stack (via `software.configure.docker-compose` role : rsync catalog -> VM without touching the VM `.env` + `docker compose up -d`)

The catalog source is `range42-catalog/03_container_layer/docker/admin/misp-standalone/`
(official misp-docker images : MariaDB + Valkey + misp-modules + misp-core + misp-nginx,
plus the certgen and provisioner one-shots ; nothing is built on the VM).

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-misp` | inventory hostname of the MISP VM |
| `global_vm_ci_ip` | `192.168.142.111` | IP of the MISP server, written to the VM `.env` as `MISP_BASEURL=https://<ip>` |

## Catalog .env handling

Play 1 auto-cps `.env.example` -> `.env` on the local catalog if `.env` is
absent, with `force: false` (respects an existing customized `.env`). This
makes a first-time deploy "just work" with the catalog's weak placeholder
secrets (`Admin1234!XYZ`, `changeme_db_password`). Populate the catalog
`.env` BEFORE running the bundle for production-like creds :

```
cd $RANGE42_INVENTORY/03_container_layer/docker/admin/misp-standalone/
cp .env.example .env
$EDITOR .env       # fill MISP_DB_PASSWORD, DB_ROOT_PASSWORD,
                   # MISP_ADMIN_PASSWORD, MISP_READER_PASSWORD,
                   # MISP_WRITER_PASSWORD, MISP_SALT (openssl rand -hex 32)
```

The catalog `.env` is gitignored (`**/.env`) so customizations stay local.

The catalog `.env` only seeds the VM `.env` on the first deploy. After that the
VM copy is authoritative : edit `/home/alice/misp-standalone/.env` on the VM
and re-run the bundle. `MISP_BASEURL` is always reset to `https://<global_vm_ci_ip>`.

## Operator user + deploy dir

The bundle hardcodes :
- operator user : `alice`
- remote deploy dir : `/home/alice/misp-standalone`

Matches the convention used by the other admin docker-compose stacks.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.misp_standalone/main.yml"
  when: INSTALL_MISP | default("NO") | upper == "YES"
  vars:
    global_vm_ssh_name: "r42.admin-misp"
    global_vm_ci_ip:    "192.168.142.111"
```

## First-boot timing

The stack pulls ~3.2 GB of pinned misp-docker images on a fresh VM. Once they
are present, MISP answers about 2 minutes after a cold start and the
provisioner finishes about 15 seconds later. Re-deploys with existing volumes
are healthy in about 30 seconds.

Watch progress with :
```
ssh r42.admin-misp
cd /home/alice/misp-standalone
sudo docker compose logs -f provisioner    # wait for "Provisioning complete."
```

Credentials end up in `/home/alice/misp-standalone/keys/` on the VM
(`api-keys.txt`, `misp-credentials.json`, root-only).

## Naming

Bundle name mirrors the catalog element name (`docker/admin/misp-standalone/`).
The "-standalone" suffix distinguishes it from a future Wazuh-style multi-host
MISP deploy if needed.
