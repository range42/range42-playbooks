# bundles/admin/software.install.nextcloud

Nextcloud docker-compose stack install bundle - 4 plays :

1. ensure catalog `.env` exists on localhost (cp `.env.example` -> `.env` if absent, force=false)
2. install Docker + docker-compose on the Nextcloud VM (via `software.install.warmup.basic_packages` role)
3. open firewall ports 22 + 8443 on the VM (via `software.configure.firewalls` role)
4. deploy nextcloud docker-compose stack on the VM (via `software.configure.docker-compose` role : rsync catalog -> VM + `docker compose up -d`)

The catalog source is `range42-catalog/03_container_layer/docker/admin/nextcloud/`
(postgres + redis + nextcloud + provisioner `build:` = 4 services).

> Note vs `software.install.misp_standalone` (3 plays) : this bundle adds an
> explicit firewall play (Play 3) to open 8443. A reusable software bundle owns
> its own service port so `INSTALL_NEXTCLOUD=YES` works in any scenario - the
> scenario baseline only opens 22.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-nextcloud-standalone` | inventory hostname of the Nextcloud VM |
| `global_vm_ci_ip` | `192.168.142.181` | IP of the Nextcloud server (informational) |

## Catalog .env handling

Mirrors the upstream catalog README Quick Start (`cp .env.example .env`). Play 1
auto-cps `.env.example` -> `.env` on the local catalog if `.env` is absent, with
`force: false` (respects an existing customized `.env`). The compose file uses
`${VAR:-default}` fallbacks for every variable, so the stack boots with or
without `.env` ; the seed lets the operator customize creds. Populate the catalog
`.env` BEFORE running the bundle for stronger creds :

```
cd $RANGE42_INVENTORY/03_container_layer/docker/admin/nextcloud/
cp .env.example .env
$EDITOR .env       # set POSTGRES_PASSWORD, NC_ADMIN_USER/PASS, HTTP_PORT,
                   # and NC_DOMAIN (see the gotcha below)
```

The catalog `.env` is gitignored (`**/.env`) so customizations stay local.

### ⚠ NC_DOMAIN gotcha (NOT auto-fixed by this bundle)

The catalog `.env.example` ships:

```
NC_DOMAIN=localhost 192.168.142.250
```

This does **NOT** include this VM's IP (`192.168.142.181`). Nextcloud's
`trusted_domains` check rejects access through any host not listed in
`NC_DOMAIN`, so browsing to `https://192.168.142.181:8443` would fail. Edit the
catalog `.env` and add this VM's IP to `NC_DOMAIN` BEFORE deploying, e.g.:

```
NC_DOMAIN=localhost 192.168.142.181
```

The bundle intentionally does NOT rewrite this for you (mirrors the upstream
README "edit `.env` before deploying" step) - it is an operator decision.

## First-boot timing + egress

The provisioner image is built from a local Dockerfile (not pulled) that fetches
`yq` / `jq` from GitHub during the build, so the VM needs **outbound egress on
first build** :
- first build : 1-3 min (provisioner sidecar image)
- bootstrap   : the provisioner waits for the Nextcloud healthcheck
  (`start_period`, retries) then seeds users + app passwords, guarded by
  `/tokens/.provisioned` (runs once)

Four services are started : `db` (postgres) + `redis` + `nextcloud` +
`provisioner`. Subsequent boots : fast (image cached, provisioner skips when
already stamped).

Watch progress with :
```
ssh r42.admin-nextcloud-standalone
cd /home/alice/nextcloud
sudo docker compose logs -f provisioner    # wait for provisioning complete
sudo docker exec nextcloud-provisioner cat /tokens/tokens.txt
```

Nextcloud web UI : `https://<global_vm_ci_ip>:8443`.

## Operator user + deploy dir

The bundle hardcodes :
- operator user : `alice`
- remote deploy dir : `/home/alice/nextcloud`

Matches the convention used by the other admin docker-compose stacks.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.nextcloud/main.yml"
  when: INSTALL_NEXTCLOUD | default("NO") | upper == "YES"
  vars:
    global_vm_ssh_name: "r42.admin-nextcloud-standalone"
    global_vm_ci_ip:    "192.168.142.181"
```

(The vitrine scenario `nextcloud_lab` defaults the flag YES ; general scenarios default NO.)

## Naming

Bundle name mirrors the catalog element name (`docker/admin/nextcloud/`).
