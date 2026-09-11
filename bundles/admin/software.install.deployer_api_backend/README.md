# Managed backend container installer

`main.yml` now consumes the authenticated backend image contract through
`files/container_apply.py`. It requires an already installed local Docker Engine
and Compose plugin, an immutable image already present in that daemon, and
explicit target-host paths. It creates no Proxmox guests and makes no firewall,
Tailscale or host-network changes.

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/admin/software.install.deployer_api_backend/main.yml"
  vars:
    global_vm_ssh_name: backend-host
    BACKEND_IMAGE: "sha256:<64-character-reviewed-image-id>"
    BACKEND_INSTALL_ROOT: /var/lib/range42-backend
    BACKEND_INSTALL_NAME: range42-backend
    BACKEND_UID: 1000
    BACKEND_GID: 1000
    API_PORT: 8000
    BACKEND_LISTEN_ADDRESS: 127.0.0.1
    BACKEND_CORS_ORIGINS: ["https://deployer.example.org"]
```

The listener defaults to loopback. Configure a reverse proxy separately or
explicitly select the interface on which the API should be reachable. Browser
operators enter the private API token through the UI connection flow. The
installer never returns that token in Ansible output.

## Actions and managed records

`BACKEND_INSTALL_ACTION` accepts:

- `apply` (default): create a fresh managed installation, or verify an unchanged
  running installation without replacing its container or rewriting its record.
- `fresh`: require a new installation; refuse an existing managed record.
- `update`: explicitly replace an existing managed installation after its
  tracked work is idle. Changes without this action are refused.

The private root contains `.installation.lock`, `installation.json`, immutable
`releases/<id>/`, and consistent database backups under `backups/<id>/`.
The record binds the exact container/image IDs, configuration and mounts,
release hashes and original credential-file hashes. Repeats check those facts
and authenticated readiness. Source runtime edits do not modify installed copies;
changed source bytes require an explicit update.

Fresh startup and updates hold the persistent HTTP admission inode through
candidate startup, internal backend readiness/runtime-profile checks and record
commit. They also write and fsync an intent on that same inode before starting
a fresh candidate or stopping the old container. The v2 API refuses new finite
requests while any intent bytes remain, even after installer exit or restart.
A candidate is created stopped and its full ID is recorded before start.
Public health stays available while authenticated finite API operations are
fenced. The image migrates SQLite before it serves; no post-start Alembic command
is used. Successful update retains the old stopped container and private backup.

A managed update first verifies the current record, credentials, runtime and
container, then uses the tested continuous host-admission/installed idle-audit
mechanism. Busy provisioning or unverifiable runner artifacts refuse before stop.
The configured workspace/database/state/credential paths, installation name and
UID/GID cannot be relocated by update. After stop, the installer takes a SQLite
backup; a failed candidate is stopped before restoring that backup and restarting
the exact prior container. The host admission lock remains held throughout.
Only verified candidate readiness plus record commit, or verified old-container readiness plus restored
record, clears and fsyncs the owned intent. Stop/inspect or rollback-readiness
failures preserve the marker when the flock closes.
After admitting new requests, a subsequent readiness failure is reported without
rolling back potentially new user data.

`pending.json` denotes incomplete installation/cutover. It blocks automatic repeat
and needs explicit operator review. It is not the API admission fence; the
nonempty original maintenance inode is. A new helper refuses preexisting intent
without clearing it. Never delete or replace that inode to resume service.
Failed candidate artifacts and backups remain private. The installer does not prune old releases, containers or backups.

## Persistent credentials and runtime

Defaults are `<root>/state`, `<state>/workspaces` and `<root>/secrets`. New
installations generate private `api-token` and `credential-key` files once.
Existing credentials are never rotated automatically. Missing, malformed,
wrong-owner or changed credential bytes refuse installation. State mounts remain
writable; the container root, credential mounts and execution runtime are read-only.
The operator's whole SSH home is never mounted.

`BACKEND_WORKSPACE_HOST`, `BACKEND_WORKSPACE_CONTAINER` and
`BACKEND_DATABASE_CONTAINER` explicitly retain both sides of a historical workspace
binding. The database must reside within that workspace. `BACKEND_STATE_DIR` and
`BACKEND_SECRETS_DIR` select the other persistent host paths. Historical data is
never silently treated as a fresh empty installation.

For execution, set **both** `BACKEND_RUNTIME_DIR` and
`BACKEND_WORKSPACE_TEMPLATE_DIR` to reviewed, complete target-host exports. The
installer copies them into a new release, preserving literal symlink targets and
file bytes, rejecting escaping links/hardlinks/special files. Expected runtime:

```text
range42-playbooks/                         # including bundles and scenarios
range42-ansible_roles-proxmox_controller/roles/
range42-catalog/02_ansible_layer/{admin,trainee}/roles/
range42-catalog/03_container_layer/docker/_ctf/
range42/roles/
collections/
ansible.cfg
proxmox-ca.pem                             # public roots plus trusted PVE CA
bundle-runtime.json                       # generated for /runtime paths
```

Generate the backend runtime manifest for the exact container environment shown
by `container_plan.compose_document`; it must bind `/runtime` dependencies and
its Ansible configuration. Candidate validation runs the image's actual
`runtime_snapshot()` against the staged read-only export. It cannot bless a new
or mismatched profile silently. The separate private workspace template supplies
only the selected vault/SSH files supported by the backend.

Without runtime/template bindings, the installation serves the authenticated
control-plane API, but it is not ready to execute infrastructure playbooks.
Register catalog sources and Proxmox hosts through authenticated UI/API flows.
This installer does not auto-seed provider or Proxmox credentials.

## Legacy mapping and remaining limits

`REMOTE_PROJECT_DIR` maps only to `BACKEND_INSTALL_ROOT`, and
`WORKSPACE_DIR_HOST` maps only to `BACKEND_WORKSPACE_HOST`. Neither alias authorizes
adoption of an existing directory. Old `LOCAL_CODE_PATH`, `PLAYBOOKS_DEST_DIR`,
`DEPLOYER_UI_CORS_REGEX` and enabled `INSTALL_TAILSCALE` inputs are refused with
migration guidance: supply a reviewed image, complete runtime, exact CORS origins
and separately prepared networking.

**Offline legacy-container adoption is still pending.** Unknown running or stopped
legacy installations and existing unrecorded workspaces are preserved/refused;
there is no implicit systemd conversion. Fresh failures and interrupted cutovers
also require operator recovery; no automatic partial-install resume is claimed.

Installer death releases its flock but retains the fsynced intent, so a v2 API
keeps finite requests fenced across restart on the same persistent inode. This
is durable admission, not automatic crash recovery or atomic Docker/database
rollback. A failed stop/inspection/backup can leave an exact container stopped
or its state unknown. Prove failed candidates stopped before restoring data;
verify the recovered container, readiness and managed bindings before any
explicit recovery clears the original inode. Arbitrarily privileged filesystem
writers, data loss and independent Proxmox operations remain outside this fence.

Local Linux inode/UID semantics are required; remote Docker daemons, user-namespace
remapping and network filesystems are unsupported. The running backend and each
candidate must implement `flock-http-intent-v2` and compatible internal readiness/
profile APIs. Before fresh startup or update, the installer probes the immutable
candidate image in a disposable container with no network, mounts or secrets.
A v1 image is refused: it ignores intent bytes. Existing v1 installations need a
reviewed offline migration; automatic online v1-to-v2 upgrade is not implemented.
An unchanged v1 repeat may still verify readiness without modifying it. Each new
image requires matched compatibility tests.

See `docs/container-installer-checkpoint.md` for exact local acceptance evidence.
No shared installation or live Proxmox acceptance is implied by these source tests.
