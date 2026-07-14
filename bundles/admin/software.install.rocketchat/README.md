# bundles/admin/software.install.rocketchat

Rocket.Chat docker-compose stack install bundle - 4 plays :

1. ensure catalog `.env` exists on localhost (cp `.env.example` -> `.env` if absent, force=false)
2. install Docker + docker-compose on the Rocket.Chat VM (via `software.install.warmup.basic_packages` role)
3. open firewall ports 22 + 3000 on the VM (via `software.configure.firewalls` role)
4. deploy rocketchat docker-compose stack on the VM (via `software.configure.docker-compose` role : rsync catalog -> VM + `docker compose up -d`)

The catalog source is `range42-catalog/03_container_layer/docker/admin/rocketchat/`
(mongodb:6.0 + mongo-init-replica + rocketchat/rocket.chat:latest + provisioner `build:` = 4 services).

> Note vs `software.install.misp_standalone` (3 plays) : this bundle adds an
> explicit firewall play (Play 3) to open 3000. A reusable software bundle owns
> its own service port so `INSTALL_ROCKETCHAT=YES` works in any scenario - the
> scenario baseline only opens 22.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-rocketchat-standalone` | inventory hostname of the Rocket.Chat VM |
| `global_vm_ci_ip` | `192.168.142.185` | IP of the Rocket.Chat server (informational) |

## Catalog .env handling

Mirrors the upstream catalog README Quick Start (`cp .env.example .env`). Play 1
auto-cps `.env.example` -> `.env` on the local catalog if `.env` is absent, with
`force: false` (respects an existing customized `.env`). The compose file uses
`${VAR:-default}` fallbacks for every variable, so the stack boots with or
without `.env` ; the seed lets the operator customize creds. The `.env` is
optional for Rocket.Chat (`RC_*` + `HTTP_PORT`, no mandatory secret) ; the seed
is kept for parity. Populate the catalog `.env` BEFORE running the bundle for
stronger creds :

```
cd $RANGE42_INVENTORY/03_container_layer/docker/admin/rocketchat/
cp .env.example .env
$EDITOR .env       # set RC_ADMIN_USER/PASS, RC_ADMIN_EMAIL, RC_BASE_URL,
                   # HTTP_PORT (must match the firewall port 3000)
```

The catalog `.env` is gitignored (`**/.env`) so customizations stay local.

## Operator user + deploy dir

The bundle hardcodes :
- operator user : `alice`
- remote deploy dir : `/home/alice/rocketchat`

Matches the convention used by the other admin docker-compose stacks.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.rocketchat/main.yml"
  when: INSTALL_ROCKETCHAT | default("NO") | upper == "YES"
  vars:
    global_vm_ssh_name: "r42.admin-rocketchat-standalone"
    global_vm_ci_ip:    "192.168.142.185"
```

(The vitrine scenario `rocketchat_lab` defaults the flag YES ; general scenarios default NO.)

## First-boot timing

The provisioner image is built from a local Dockerfile (not pulled) and the
stack uses a MongoDB replica-set :
- first build : 1-3 min (provisioner sidecar image)
- cold-start convergence : ~90-180 s on first deploy. The `mongo-init-replica`
  container initialises the `rs0` replica set (`rs.initiate()`), then the
  `rocketchat` healthcheck (`start_period 60s`, 15 retries) must pass before the
  `provisioner` seeds users + personal access tokens. `mongo-init-replica` and
  `provisioner` are one-shot (`restart: "no"`).

Subsequent boots : fast (image cached, replica set already initialised, tokens
already provisioned). Re-runs are idempotent.

Watch progress with :
```
ssh r42.admin-rocketchat-standalone
cd /home/alice/rocketchat
sudo docker compose logs -f provisioner    # wait for provisioning complete
sudo docker exec rocketchat-provisioner cat /tokens/tokens.txt
```

Rocket.Chat web UI : `http://<global_vm_ci_ip>:3000`.
Default admin credentials : `rc-admin` / `Admin1234!` (change via the catalog `.env`).

## Naming

Bundle name mirrors the catalog element name (`docker/admin/rocketchat/`).
