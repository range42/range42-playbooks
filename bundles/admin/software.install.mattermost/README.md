# bundles/admin/software.install.mattermost

Mattermost docker-compose stack install bundle - 4 plays :

1. ensure catalog `.env` exists on localhost (cp `.env.example` -> `.env` if absent, force=false)
2. install Docker + docker-compose on the Mattermost VM (via `software.install.warmup.basic_packages` role)
3. open firewall ports 22 + 8065 on the VM (via `software.configure.firewalls` role)
4. deploy mattermost docker-compose stack on the VM (via `software.configure.docker-compose` role : rsync catalog -> VM + `docker compose up -d`)

The catalog source is `range42-catalog/03_container_layer/docker/admin/mattermost/`
(postgres:16-alpine + mattermost-team-edition + provisioner `build:` = 3 services).

> Note vs `software.install.misp_standalone` (3 plays) : this bundle adds an
> explicit firewall play (Play 3) to open 8065. A reusable software bundle owns
> its own service port so `INSTALL_MATTERMOST=YES` works in any scenario - the
> scenario baseline only opens 22.

## Required vars

| var | example | purpose |
|-----|---------|---------|
| `global_vm_ssh_name` | `r42.admin-mattermost-standalone` | inventory hostname of the Mattermost VM |
| `global_vm_ci_ip` | `192.168.142.182` | IP of the Mattermost server (informational) |

## Catalog .env handling

Mirrors the upstream catalog README Quick Start (`cp .env.example .env`). Play 1
auto-cps `.env.example` -> `.env` on the local catalog if `.env` is absent, with
`force: false` (respects an existing customized `.env`). The compose file uses
`${VAR:-default}` fallbacks for every variable, so the stack boots with or
without `.env` ; the seed lets the operator customize creds. Populate the catalog
`.env` BEFORE running the bundle for stronger creds :

```
cd $RANGE42_INVENTORY/03_container_layer/docker/admin/mattermost/
cp .env.example .env
$EDITOR .env       # set POSTGRES_PASSWORD, MM_ADMIN_USER/PASS (must match
                   # provisioning/users.yml admins[0]), MM_TEAM_NAME
```

The catalog `.env` is gitignored (`**/.env`) so customizations stay local.

## Operator user + deploy dir

The bundle hardcodes :
- operator user : `alice`
- remote deploy dir : `/home/alice/mattermost`

Matches the convention used by the other admin docker-compose stacks.

## Call-site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.mattermost/main.yml"
  when: INSTALL_MATTERMOST | default("NO") | upper == "YES"
  vars:
    global_vm_ssh_name: "r42.admin-mattermost-standalone"
    global_vm_ci_ip:    "192.168.142.182"
```

(The vitrine scenario `mattermost_lab` defaults the flag YES ; general scenarios default NO.)

## First-boot timing

The provisioner image is built from a local Dockerfile (not pulled) :
- first build : 1-3 min (provisioner sidecar image)
- bootstrap   : the provisioner waits for the mattermost healthcheck
  (`start_period 60s`, 15 retries) then seeds users + personal access tokens,
  guarded by `/tokens/.provisioned` (runs once)

Subsequent boots : fast (image cached, provisioner skips when already stamped).

Watch progress with :
```
ssh r42.admin-mattermost-standalone
cd /home/alice/mattermost
sudo docker compose logs -f provisioner    # wait for provisioning complete
sudo docker exec mattermost-provisioner cat /tokens/tokens.txt
```

Mattermost web UI : `http://<global_vm_ci_ip>:8065`.

## Naming

Bundle name mirrors the catalog element name (`docker/admin/mattermost/`).
