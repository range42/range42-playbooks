# bundles/admin/software.install.deployer-ui

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

## Call-site example

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_GITDIR__ROOT_DIR') }}/range42-playbooks/bundles/admin/software.install.deployer-ui/main.yml"
  vars:
    global_vm_ssh_name: "r42.admin-deployer-ui"
    global_vm_ci_ip:    "192.168.142.103"
```

## What runs

1. **Docker install** : invokes `software.install.warmup.basic_packages` role with `INSTALL_PACKAGES_DOCKER=YES` + `INSTALL_PACKAGES_DOCKER_COMPOSE=YES` (gets Docker Engine + compose plugin via the project's standard install path)
2. **Firewall** : applies `software.configure.firewalls` role with rules for ports 22 + UI_PORT
3. **Sync source** : rsync's the deployer-ui repo from the controller to `REMOTE_PROJECT_DIR` (excludes `.git`, `node_modules`, `dist`, `.env*`)
4. **Template .env** : writes `UI_PORT=<port>` to `<REMOTE_PROJECT_DIR>/.env` for docker-compose to pick up
5. **Compose up** : runs `docker compose up -d --build` in the project dir (builds the multi-stage image locally on the VM the first time, reuses cached layers afterwards)
6. **Verify** : waits for the UI port + probes `/health` (expects HTTP 200, content `ok`)

## Backend connection (CORS path)

The bundled `nginx/default.conf` from the deployer-ui repo serves only the SPA + `/health`. It does NOT proxy `/v1`, `/v0`, `/ws` to the backend. This bundle therefore relies on the **CORS path** :

- The backend (deployer-api-backend) must allow the UI's origin in `Access-Control-Allow-Origin`
- The backend URL is configured at runtime via the in-app **Settings** modal (no build-time env var needed)
- Operator workflow : open the UI in a browser → Settings → set backend URL → done

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
