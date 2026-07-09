# bundles/admin/software.install.gitea

Gitea docker-compose stack install bundle - 4 plays :

1. ensure catalog `.env` exists on localhost (cp `.env.example` -> `.env` if absent, force=false)
2. install Docker + docker-compose on the Gitea VM (via `software.install.warmup.basic_packages` role)
3. open firewall ports 22 + 3000 + 2222 on the VM (via `software.configure.firewalls` role)
4. deploy gitea docker-compose stack on the VM (via `software.configure.docker-compose` role : rsync catalog -> VM + `docker compose up -d`)

The catalog source is `range42-catalog/03_container_layer/docker/admin/gitea/`
(postgres + gitea + provisioner `build:` = 2 services postgres + gitea, automated user/SSH-key provisioning).

Gitea is a self-hosted git server. It exposes TWO service endpoints :
- HTTP web UI / API on host port **3000**
- Git over SSH on host port **2222** (offset from the host sshd on 22)

> Note vs `software.install.misp-standalone` (3 plays) : this bundle adds an
> explicit firewall play (Play 3) to open 3000 + 2222. A reusable software
> bundle owns its own service ports so `INSTALL_GITEA=YES` works in any
> scenario - the scenario baseline only opens 22.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-gitea-standalone` | inventory hostname of the Gitea VM |
| `global_vm_ci_ip` | `192.168.142.183` | IP of the Gitea server (informational) |

## Catalog .env handling

Mirrors the upstream catalog README Quick Start (`cp .env.example .env`). Play 1
auto-cps `.env.example` -> `.env` on the local catalog if `.env` is absent, with
`force: false` (respects an existing customized `.env`). The compose file uses
`${VAR:-default}` fallbacks for every variable, so the stack boots with or
without `.env` ; the seed lets the operator customize creds. Populate the catalog
`.env` BEFORE running the bundle for stronger creds :

```
cd $RANGE42_INVENTORY/03_container_layer/docker/admin/gitea/
cp .env.example .env
$EDITOR .env       # set GITEA_SECRET_KEY (openssl rand -hex 32),
                   # GITEA_INTERNAL_TOKEN, POSTGRES_PASSWORD,
                   # GITEA_ADMIN_USER/PASS (must match
                   # provisioning/users.yml admins[0])
```

The catalog `.env` is gitignored (`**/.env`) so customizations stay local.

## Operator user + deploy dir

The bundle hardcodes :
- operator user : `alice`
- remote deploy dir : `/home/alice/gitea`

Matches the convention used by the other admin docker-compose stacks.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/admin/software.install.gitea/main.yml"
  when: INSTALL_GITEA | default("NO") | upper == "YES"
  vars:
    global_vm_ssh_name: "r42.admin-gitea-standalone"
    global_vm_ci_ip:    "192.168.142.183"
```

(The vitrine scenario `gitea_lab` defaults the flag YES ; general scenarios default NO.)

## First-boot timing

The provisioner image is built from a local Dockerfile (not pulled) :
- first build : 1-3 min (provisioner sidecar image)
- bootstrap   : the provisioner waits for the gitea healthcheck then seeds
  users + SSH keys declared in `provisioning/users.yml`, guarded by
  `/data/gitea/.provisioned` (runs once)

Subsequent boots : fast (image cached, provisioner skips when already stamped).

Watch progress with :
```
ssh r42.admin-gitea-standalone
cd /home/alice/gitea
sudo docker compose logs -f provisioner    # wait for provisioning complete
```

Gitea web UI : `http://<global_vm_ci_ip>:3000`.
Git over SSH : `git clone git@<global_vm_ci_ip>:2222/<org>/<repo>.git`.

## Naming

Bundle name mirrors the catalog element name (`docker/admin/gitea/`).
