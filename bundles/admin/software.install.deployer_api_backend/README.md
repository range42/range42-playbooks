# software.install.deployer_api_backend

Install the application-owned API container through the existing native software
bundle. The backend uses Python 3.12, startup Alembic migrations, required bearer
authentication and a persistent credential encryption key. The installer accepts
preprovisioned private inputs; it does not generate credentials or export a new
execution runtime.

## Required installation inputs

Alongside `global_vm_ssh_name` and `global_vm_ci_ip`, supply:

| Input | Required content |
| --- | --- |
| `API_SECRETS_DIR_HOST` | Real 0700 directory containing existing 0600 `api-token` and `credential-key`, owned by `API_CONTAINER_UID`. |
| `RUNTIME_DIR_HOST` | Complete reviewed playbooks/controller/catalog/core/devkit/collections export, strict `ansible.cfg`, combined public/PVE roots, and `bundle-runtime.json` for `/runtime` paths and this Compose environment. |
| `WORKSPACE_TEMPLATE_DIR_HOST` | Private vault/password/key/known_hosts template, with real 0700 directories and regular 0600 files, without symlinks. |
| `API_HOME_DIR_HOST` | Dedicated 0700 container home with `.ssh/config`, `.ssh/config_range42-<context>`, `.ssh/range42/<context>/` keys, verified known_hosts and `.zshrc`. Default `/var/lib/range42/backend-home`. |
| `WORKSPACE_DIR_HOST` | Existing 0700 native workspace root, default `/home/range42/range42.config`, containing the selected `<codename>-<scenario>` context. |

Prepare the context using core's existing workspace roles and scenario templates.
Inside the container, home is `/home/range42` and the context root is
`/home/range42/range42.config`. Render the native sourced environment for
`RANGE42_GITDIR__ROOT_DIR=/runtime`, and the inventory/SSH aliases for these
container paths. The context requires `sourced_range42.sh`, `scenario`,
`inventory/inventory_default.yml`, `secrets/default_vault.yml` and
`secrets/vault_pass.txt`. Keep machine automation credentials separate from human
operator credentials. The immutable credential template is a separate input,
not a copy of the native workspace's symlink layout.

The matching core revision supports runner-owned repository credential links.
The backend's existing native adapter opts into that behavior because it already
copies the saved scenario and links credentials privately for each attempt.
Ordinary CLI selection retains its existing shared-link workflow; standalone
source-based devkit commands still need their normal writable checkout.

Generate and verify the runtime profile with the application's existing
`app.core.bundle_runtime.build_runtime_manifest` function under the exact container
paths/environment. Include `RANGE42_GITDIR__ROOT_DIR=/runtime`, as set by this
bundle's override. Supply the matching reviewed backend/playbooks/core revisions.
The bundle refuses incomplete contexts or drift before starting the service.

## Native call site

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.deployer_api_backend/main.yml"
  vars:
    global_vm_ssh_name: r42.admin-deployer-api-backend
    global_vm_ci_ip: 192.0.2.20
    API_SECRETS_DIR_HOST: /var/lib/range42/private/api-secrets
    RUNTIME_DIR_HOST: /opt/range42/runtime
    WORKSPACE_TEMPLATE_DIR_HOST: /var/lib/range42/private/workspace-template
    API_HOME_DIR_HOST: /var/lib/range42/backend-home
    WORKSPACE_DIR_HOST: /home/range42/range42.config
    BACKEND_CORS_ORIGINS: https://staff.example.test
```

Use `range42-context use <codename> <scenario>` on the controller before invoking
the bundle. Vault inputs for registration remain `proxmox_api_host`,
`proxmox_node`, `proxmox_api_user`, `proxmox_api_token_id` and
`proxmox_api_token_secret`. The hostname must match its certificate, and the
execution network must reach the API and guest SSH paths.

## Installation and repeat runs

The bundle validates inputs before changing the host, retains the existing
Docker/firewall/optional-Tailscale roles, syncs only the API build context,
records native source provenance, renders current Compose inputs, builds, verifies
the runtime/private context and stopped state, then starts the API. Application
startup validates credentials and runs migrations before serving. Public
`/v1/health` is followed by bearer-authenticated Proxmox registration and readiness
with `ready: true`. Token and registration tasks use `no_log`.

`API_PORT` retains its existing meaning, default 8000. `BACKEND_LISTEN_ADDRESS`
defaults to the packaged loopback listener; remote exposure requires an explicit
listener and the existing TLS/access policy. `API_CONTAINER_UID`/`GID` default to
1000 and must match private file ownership. Both the existing CORS regex parameter
and `BACKEND_CORS_ORIGINS` are passed to the actual container environment.
The single-worker application command and read-only source/runtime mounts are
unchanged. `INSTALL_TAILSCALE` retains its existing behavior and defaults to NO.

A running API is refused before source sync or container replacement. Use the
backend's documented maintenance drain/stop procedure for an update, preserve
state and both credential files, then rerun this bundle against the stopped
installation. This compatibility patch does not automate a running cutover.
Stopped state with nonterminal attempts, workspace locks, inconsistent runner
artifacts or existing maintenance intent is refused. Readiness is checked after
Proxmox registration and can therefore fail until private routing/trust works.

The old bundle copied only playbooks and performed a post-start migration. Its
`PLAYBOOKS_DEST_DIR` input is replaced by the explicit complete `RUNTIME_DIR_HOST`
input. Existing caller files must supply the new private inputs. Retain old DB
and attempt paths during migration; never use a fresh empty directory as an
implicit import of an existing installation. Backup/restore covers API state,
native home/workspaces and both credential files together.

## Validation

Regression tests render actual Ansible copy tasks against backend Compose and
check port/UID/CORS, persistent mounts, secret inputs and authenticated probes.
Disposable installation acceptance exercises the native packaging tasks with
synthetic secrets and a localhost-only scenario. The core, backend adapter and
runtime fingerprint tests verify the same native execution contract. No live
hypervisor deployment is performed by these tests.
