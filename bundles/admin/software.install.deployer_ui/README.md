# bundles/admin/software.install.deployer_ui

Deploys range42-deployer-ui as a Docker container, following the canonical
deploy method shipped by the [range42-deployer-ui repo](../../../range42-deployer-ui/)
(multi-stage Dockerfile + docker-compose + nginx serving the SPA bundle).

## Why Docker

The upstream repo ships a multi-stage Dockerfile :

1. **Build stage** (`node:24-bookworm-slim`) : `npm ci` + `vite build` → produces optimised SPA bundle in `/app/dist`
2. **Runtime stage** (`nginx:stable-bookworm`) : serves the bundle on port 80 with gzip, security headers, `/health` endpoint, SPA fallback, long-lived asset cache

`docker-compose.yml` provides the canonical service definition with healthcheck and host port mapping. This bundle wires that into an ansible-driven deploy.

## Required vars

| var | meaning |
|---|---|
| `global_vm_ssh_name` | inventory hostname for the deployer-ui VM (e.g. `r42.admin-deployer-ui`) |
| `global_vm_ci_ip` | IP of the deployer-ui VM (informational ; not consumed by the plays) |

## Optional vars (with defaults)

| var | default |
|---|---|
| `LOCAL_CODE_PATH` | `{{ env RANGE42_GITDIR__ROOT_DIR }}/range42-deployer-ui/` |
| `REMOTE_PROJECT_DIR` | `/var/www/range42_deployer_ui` |
| `UI_PORT` | `3000` |
| `BACKEND_API_URL` | *(unset)* — when set, rendered into `public/config.json` so the SPA pre-registers this backend |
| `PROXMOX_NODE_NAME` | `pve` — paired with `BACKEND_API_URL` in `config.json` |

## Call-site example

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.deployer_ui/main.yml"
  vars:
    global_vm_ssh_name: "r42.admin-deployer-ui"
    global_vm_ci_ip:    "192.168.142.103"
```

## What runs

1. **Docker install** : invokes `software.install.warmup.basic_packages` role with `INSTALL_PACKAGES_DOCKER=YES` + `INSTALL_PACKAGES_DOCKER_COMPOSE=YES` (gets Docker Engine + compose plugin via the project's standard install path)
2. **Firewall** : applies `software.configure.firewalls` role with rules for ports 22 + UI_PORT
3. **Sync source** : rsync's the deployer-ui repo from the controller to `REMOTE_PROJECT_DIR` (excludes `.git`, `node_modules`, `dist`, `.env*`)
4. **Record provenance** : captures the controller-side `ref` / short `sha` / dirty-file count of the synced tree into `/var/lib/range42/deployer_ui.version` and echoes it in the play output
5. **Template .env** : writes `UI_PORT=<port>` to `<REMOTE_PROJECT_DIR>/.env` for docker-compose to pick up
6. **Render config.json** (only when `BACKEND_API_URL` is set) : writes `<REMOTE_PROJECT_DIR>/public/config.json` before the build, so vite copies it into `dist/` and nginx serves it next to `index.html`
7. **Compose up** : runs `docker compose up -d --build` in the project dir (builds the multi-stage image locally on the VM the first time, reuses cached layers afterwards)
8. **Verify** : waits for the UI port + probes `/health` (expects HTTP 200, content `ok`)

## Source provenance

This bundle deploys the **controller's working tree**, not a git clone : branch, local commits and uncommitted edits all ship as-is. That is what makes a dev lab fast (edit, redeploy, no push round-trip), but it also means the deployed bundle can exist on no git remote.

Step 4 therefore records what was actually shipped :

```
# /var/lib/range42/deployer_ui.version
repo=range42-deployer-ui
source_path=/home/alice/range42-deployer-ui/
ref=dev
sha=a1b2c3d
dirty=4
deployed_at=2026-08-10T09:12:44Z
```

`dirty=0` is the only evidence that what runs on the VM matches a pushed commit. The file lives outside `REMOTE_PROJECT_DIR` on purpose — inside, its timestamp would bust the Docker build cache on every no-op re-run.

## Backend connection (CORS path)

The bundled `nginx/default.conf` from the deployer-ui repo serves only the SPA + `/health`. It does NOT proxy `/v1`, `/v0`, `/ws` to the backend. This bundle therefore relies on the **CORS path** :

- The backend (deployer-api-backend) must allow the UI's origin in `Access-Control-Allow-Origin`
- The backend URL comes from `config.json` when `BACKEND_API_URL` is set at the call-site, otherwise from the in-app **Settings** modal
- Operator workflow with `BACKEND_API_URL` : open the UI in a browser → the backend is already registered → done
- Operator workflow without it : open the UI → Settings → set backend URL → done

The seed is a first-launch default, not a lock : the SPA only applies it when no backend has been registered yet, and records that it was offered, so a host the operator deletes stays deleted.

This is the simplest path for the POC. Production hardening options (out of scope) :

- Add an external reverse proxy (Traefik) in front of the container to terminate TLS + proxy `/v1`/`/v0`/`/ws` to the backend (eliminates CORS, single origin)
- Extend `nginx/default.conf` upstream in the repo with `location /v1 { proxy_pass http://backend:port; }` (couples UI image to backend hostname ; less portable)

## Manual verification

From the deployer-ui host, after deploy :

```bash
docker compose -f /var/www/range42_deployer_ui/docker-compose.yml ps
curl -s http://127.0.0.1:3000/health             # expect: ok
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/   # expect: 200 (SPA index.html)
```

From a peer host in the same subnet :

```bash
curl -s http://r42.admin-deployer-ui:3000/health
```

## Upgrade path (deferred)

- **Image-based deploys** : build & push `ghcr.io/range42/range42-deployer-ui:<short-sha>` from CI on the deployer-ui repo, then swap this bundle to `docker compose pull && docker compose up -d` with a tag pinned in inventory (eliminates the rsync-from-controller pattern and the reproducibility gap)
- **TLS + reverse proxy** : add a `software.configure.traefik` or extend the existing nginx config to terminate TLS and proxy the backend
- **Stop syncing source** : once on image-based deploys, the only artifact on the VM is the `docker-compose.yml` + `.env`

## Notes

- The deployer-ui is **stateless** (browser localStorage + IndexedDB via `idb`) — no volumes, no database, no persistent state on the VM. The container is safe to recreate.
- Node version in the Dockerfile builder is `24-bookworm-slim` ; `package.json` engines = `^20.19.0 || ^22.12.0 || ^24.0.0`. The host doesn't run Node — only Docker.
- The bundle assumes the controller (deployer-cli) has a working copy of the deployer-ui repo at `$RANGE42_GITDIR__ROOT_DIR/range42-deployer-ui/`. If a different checkout location is needed, override `LOCAL_CODE_PATH`.
