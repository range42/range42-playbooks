# bundles/admin/software.install.misp-standalone

MISP standalone docker-compose stack install bundle - 3 plays :

1. ensure catalog `.env` exists on localhost (cp `.env.example` -> `.env` if absent, force=false)
2. install Docker + docker-compose on the MISP VM (via `software.install.warmup.basic_packages` role)
3. deploy misp-standalone docker-compose stack on the VM (via `software.configure.docker-compose` role : rsync catalog -> VM + `docker compose up -d`)

The catalog source is `range42-catalog/03_container_layer/docker/admin/misp-standalone/`
(MariaDB + Redis + misp-modules + misp + provisioner = 5 services).

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-misp` | inventory hostname of the MISP VM |
| `global_vm_ci_ip` | `192.168.142.111` | IP of the MISP server (informational) |

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

## Operator user + deploy dir

The bundle hardcodes :
- operator user : `alice`
- remote deploy dir : `/home/alice/misp-standalone`

Matches the convention used by the other admin docker-compose stacks.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/admin/software.install.misp-standalone/main.yml"
  when: INSTALL_MISP | default("NO") | upper == "YES"
  vars:
    global_vm_ssh_name: "r42.admin-misp"
    global_vm_ci_ip:    "192.168.142.111"
```

## First-boot timing

The MISP image is built from source (not pulled) :
- first build : 10-20 min (git clone MISP + submodules + apt + composer)
- bootstrap   : 3-5 min after build (provisioner sidecar seeds DB + writes API keys)

Subsequent boots : fast (image cached).

Watch progress with :
```
ssh r42.admin-misp
cd /home/alice/misp-standalone
sudo docker compose logs -f provisioner    # wait for "Provisioning complete."
```

API keys + credentials end up in `/keys/api-keys.txt` inside the misp service container.

## Naming

Bundle name mirrors the catalog element name (`docker/admin/misp-standalone/`).
The "-standalone" suffix distinguishes it from a future Wazuh-style multi-host
MISP deploy if needed.
