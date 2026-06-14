# bundles/admin/software.install.deployer-api-backend

Deploys range42-backend-api as a Docker container, following the canonical
deploy method shipped by the [range42-backend-api repo](../../../range42-backend-api/)
(multi-stage Dockerfile + docker-compose + Python 3.13 + FastAPI + uvicorn +
embedded SQLite via SQLAlchemy async + Alembic migrations + ansible-runner
bundled inside the image).

## Architecture (POC)

```
UI (r42.admin-deployer-ui:3000)
   │
   │ CORS (UI Settings modal points here)
   ▼
Backend (r42.admin-deployer-api-backend:8000)
   ├─ SQLite DB + events.jsonl  (bind-mounted from /home/range42/range42.config on host)
   ├─ SSH keys                    (bind-mounted RO from ~/.ssh on host)
   ├─ Per-deployment secrets      (each <C>-<S>/secrets/vault_pass.txt is reachable
   │                                under /home/range42/range42.config via the same mount)
   └─ ansible-core 2.19 + runner  (bundled in the image, used by backend to drive Proxmox)
```

Kong is parallel/not in the UI->backend path for this POC (kong.yml is empty).

## Required vars

| var | meaning |
|---|---|
| `global_vm_ssh_name` | inventory hostname for the backend VM (e.g. `r42.admin-deployer-api-backend`) |
| `global_vm_ci_ip` | IP of the backend VM (informational, not consumed) |

## Optional vars (with defaults)

| var | default |
|---|---|
| `LOCAL_CODE_PATH` | `{{ env RANGE42_GITDIR__ROOT_DIR }}/range42-backend-api/` |
| `REMOTE_PROJECT_DIR` | `/var/www/range42_backend_api` |
| `API_PORT` | `8000` |
| `WORKSPACE_DIR_HOST` | `/home/range42/range42.config` |
| `DEPLOYER_UI_CORS_REGEX` | `^https?://r42\.admin-deployer-ui(:\d+)?$` |

## Call-site example

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/admin/software.install.deployer-api-backend/main.yml"
  vars:
    global_vm_ssh_name: "r42.admin-deployer-api-backend"
    global_vm_ci_ip:    "192.168.142.102"
```

## What runs

The bundle mirrors the upstream README's Quick Start - Option 1 (Docker) :
`docker compose up` against an image built from local source. No source
bind-mount at runtime ; code, playbooks, and inventory are baked into the
image at build time. Schema bootstrap is handled in-process by the app on
startup, so no explicit migration step is needed.

1. **Docker install** : invokes `software.install.warmup.basic_packages` role with `INSTALL_PACKAGES_DOCKER=YES` + `INSTALL_PACKAGES_DOCKER_COMPOSE=YES` (Docker Engine + compose plugin via the project's standard install path)
2. **Firewall** : applies `software.configure.firewalls` role with rules for ports 22 + API_PORT
3. **Workspace dir** : creates `/home/range42/range42.config/` on the host owned by UID/GID 1000 (mode 0700) - holds the SQLite DB + events.jsonl + ansible-runner artefacts + per-deployment `<C>-<S>/secrets/vault_pass.txt` ; persists across container restarts
4. **Sync source (build context)** : rsync's the backend-api repo from the controller to `REMOTE_PROJECT_DIR` (excludes `.git`, `.venv`, `collections`, `__pycache__`, `.pytest_cache`, `.env*`). This is the Docker build context only - the source is BAKED into the image at build time, NOT bind-mounted at runtime
5. **Render .env** : writes the env file consumed by docker compose (PORT, UID/GID, IMAGE_NAME, SSH_KEY_PATH, VAULT_PASSWORD_FILE empty by default, CORS_ORIGIN_REGEX, RANGE42_WORKSPACE_ROOT, WEB_CONCURRENCY=1, UVICORN_WORKERS=1, DEBUG=false)
6. **Render docker-compose.override.yml** : single runtime bind-mount of the workspace dir. The upstream compose's SSH key mount is preserved.
7. **Compose up** : `docker compose up -d --build` builds the multi-stage image locally on the VM the first time (Python 3.13 builder + slim runtime), then starts the container
8. **Verify** : waits for the API port + probes `/docs/openapi.json` (same endpoint the container's HEALTHCHECK uses) - expects HTTP 200

## CORS configuration

The backend uses Starlette's `CORSMiddleware` with `allow_origin_regex` read
from the `CORS_ORIGIN_REGEX` env var. The bundle defaults to a regex that
matches the demo_lab_bundles UI hostname (`http(s)://r42.admin-deployer-ui:<any-port>`).

For other scenarios, override `DEPLOYER_UI_CORS_REGEX` in the call-site :

```yaml
vars:
  DEPLOYER_UI_CORS_REGEX: '^https?://ui\.lab\.example\.com$'
```

The regex must be anchored (`^...$`) and properly escape literal dots. The
backend disables auth at this layer (Kong's job in a full deployment) - CORS
is defense-in-depth only.

## Database (SQLite + Alembic)

Embedded SQLite via SQLAlchemy 2.x async + aiosqlite + Alembic for migrations.
No separate Postgres / MySQL container. The DB file lives at
`/home/range42/range42.config/.range42.db` inside the container, which is
bind-mounted from `WORKSPACE_DIR_HOST` on the host (default
`/home/range42/range42.config`).

Backend invariant : the workspace dir MUST be on a local FS (ext4 / xfs /
btrfs / zfs / tmpfs). The backend refuses NFS / CIFS / FUSE at deployment-
create with HTTP 409 / `WORKSPACE_NON_LOCAL_FS`. The bundle uses a host path
that is local FS by construction (system disk).

Schema bootstrap is handled in-process by the app on startup (per the
upstream README's Quick Start - `docker compose up` is sufficient). No
explicit `alembic upgrade head` step in the bundle. If a future schema
bump requires manual migration, run it once on the host with the source
tree available :

```bash
cd /var/www/range42_backend_api
docker run --rm -v "$(pwd)/alembic.ini:/app/alembic.ini:ro" \
                -v "$(pwd)/alembic:/app/alembic:ro" \
                --env-file .env \
                range42-backend-api:local \
                alembic upgrade head
```

## Vault password file

The backend reads `VAULT_PASSWORD_FILE` at runtime to decrypt ansible-vault-
encrypted variables in playbooks it executes. The bundle leaves
`VAULT_PASSWORD_FILE=` empty in `.env` (matches upstream `.env.example`) - no
global default is set at deploy time.

Each operator-managed workspace already ships its own vault password file at
`<workspace>/secrets/vault_pass.txt`. Since the bundle bind-mounts the whole
workspace dir at `/home/range42/range42.config`, every deployment's
`vault_pass.txt` is reachable inside the container at
`/home/range42/range42.config/<C>-<S>/secrets/vault_pass.txt`. The backend
resolves the per-deployment path at runtime via the deployment id ; no
separate file copy is needed.

## Single-worker invariant

`WEB_CONCURRENCY=1` and `UVICORN_WORKERS=1` are hard-set in `.env`. The
backend keeps SSE (Server-Sent Events) state in-process ; running multiple
worker processes silently corrupts that state. The backend logs
`multi_worker_deploy_invariant_violated` if these env vars are overridden
to something other than 1.

## Manual verification

From the backend host, after deploy :

```bash
sudo docker compose -f /var/www/range42_backend_api/docker-compose.yml ps
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/docs/openapi.json   # expect: 200
curl -s http://127.0.0.1:8000/v1/health | jq                                       # expect: {"status":"ok",...}
```

From a peer host in the same subnet (e.g. the deployer-ui) :

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://r42.admin-deployer-api-backend:8000/docs/openapi.json
```

From the UI side : open `http://r42.admin-deployer-ui:3000/` in a browser,
go to Settings, set backend URL to `http://r42.admin-deployer-api-backend:8000`,
verify connectivity. The browser will send the Origin header
`http://r42.admin-deployer-ui:3000` which matches the default `CORS_ORIGIN_REGEX`.

## Upgrade path (deferred)

- **Image-based deploys** : build & push `ghcr.io/range42/range42-backend-api:<short-sha>` from CI on the backend repo, then swap this bundle to `docker compose pull && docker compose up -d` against a pinned tag in inventory (eliminates the rsync + local build pattern and the 5-10 min first-build wait on the VM)
- **Reverse proxy / TLS** : front the backend with Traefik or extend the kong gateway to proxy `/v1`, `/v0`, `/ws` (eliminates the CORS dependency, single origin for the UI)
- **Backup** : daily `sqlite3 .backup` cron or restic snapshot of the workspace dir
- **Cross-scenario migration** : same bundle import pattern, swappable into demo_lab, bs2 / bs4 / bs6 later

## Known limitations (POC)

- Vault password file is copied verbatim from controller to host - no rotation, no secret-manager integration. Operator workflow : rotate the file on the controller, re-run the bundle.
- WEB_CONCURRENCY=1 means single-process throughput. Acceptable for POC ; production scale-out requires backend changes upstream (SSE state would need to move out of process).
- Backend exposes port 8000 directly to peers in the lab subnet. No TLS. CORS regex protects browser-side. Fine for POC ; production needs TLS + reverse proxy.
