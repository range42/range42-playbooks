# Container installer checkpoint — integration incomplete, 2026-09-11

Worktree: `/tmp/r42-container-installer-next-wave`, branch
`fix/backend-container-installer-20260911`, based on playbooks `a150867`.
Credential checkpoint: `22e045d`; planner checkpoint: `d6b0698`.
The root handoff remains
`_local-specs/2026-09-11-container-installer-handoff.md` in the shared project root.

## Saved planner and credential slice

`files/container_plan.py` validates explicit installation configuration and
renders the authenticated Compose contract without creating state. It requires
an immutable image ID/digest, retains configured legacy workspace/database
locations, uses token/key file mounts, and supplies runtime/template bindings
when configured. It does not mount the operator's SSH home. The planner and
credential primitive have 21 focused passing tests; their original red/green
logs remain `/tmp/r42-container-plan-{red,green}.log`.

## Verified held-maintenance mechanism

`files/container_maintenance.py` provides a local Docker transport and the
`stopped_container(...)` context manager. Its caller supplies the authenticated
maintenance capability, full immutable container ID, explicit installation and
state paths, and API UID/GID. It verifies ownership labels, the running process,
image/configuration, and the writable state mount against the exact admission
inode reported by the API. Container names and remote Docker contexts are not
accepted. Inspect mount order is normalized while every mount field and its
multiplicity remain part of identity comparison.

The installer acquires the existing host admission inode exclusively **before**
the idle audit and retains that same descriptor through old-container stop and
the caller's replacement scope. The installer-owned
`files/container_maintenance_probe.py` runs inside that exact container and
reuses the installed backend's process/inode checks, strict attempt/artifact
audit and provisioning lock. It also holds a SQLite writer transaction and its
stdin pipe until controlled stop. No proof, credential or helper stderr is
printed. The host requires a bounded, identity-bound idle acknowledgement
before issuing stop, then verifies that exact container is stopped before
allowing replacement work.

The original stop-then-reacquire design failed a regression: losing the helper
between its last liveness check and Docker stop reopened HTTP admission. The
continuous host fence closes that window. Probe/pipe loss cannot release the
host's admission lock. This implementation leaves backend source and its
`flock-http-v1` protocol unchanged; its small probe deliberately depends on the
installed backend validator functions, so each future backend image needs the
compatibility acceptance below.

The focused regressions cover malformed/partial replies, held stdin lifetime,
exact ID and binding changes, helper loss before and during stop, lock
contention, replacement inode detection, stop refusal, and local daemon
selection. The former pending tests are now active. Disposable Docker tests
also verify unfenced-probe refusal, busy provisioning and malformed orphan
refusal without stopping the old API, plus both successful stop and deliberate
probe SIGKILL while the old API still runs. A replacement starts on the same
inode while finite authenticated HTTP and raw v0 writes remain blocked (503),
public liveness remains available and authentication still rejects missing
credentials (401). Releasing the host context restores authenticated readiness.

Acceptance image, already present locally and used by immutable ID:

```
sha256:c025beb8c3bfd7299aa9addee69e9dfbae2515f88939344e06279f2cd72070c1
```

Reproduce the focused suite from this worktree:

```sh
RANGE42_INSTALLER_MAINTENANCE_TEST_IMAGE=sha256:c025beb8c3bfd7299aa9addee69e9dfbae2515f88939344e06279f2cd72070c1 \
  pytest -q tests/test_backend_container_installer.py \
    tests/test_backend_container_plan.py \
    tests/test_backend_container_maintenance.py \
    tests/test_backend_container_maintenance_docker.py
```

Without the explicit image variable, the two Docker cases are skipped. They
create only uniquely named disposable containers, private synthetic credentials
and loopback listeners; cleanup removes their recorded full IDs. No PVE, shared
systemd installation, provider, runtime pin or upstream SDN changes occur.
The final focused run passed **51 tests** (49 host/unit cases and two actual
Docker cases) in 25.93 seconds. Focused Ruff checks pass for the implementation
and tests. Independent read-only review found no remaining false-idle blocker
within the caller obligations below. Detailed result:
`/tmp/r42-installer-maintenance-final.log`. Earlier red/green evidence:
`/tmp/r42-installer-continuous-admission-{red,green}.log` and
`/tmp/r42-installer-maintenance-docker-green.log`.

## Caller obligations and limitations

- Serialize installation changes. This primitive does not provide a whole
  release/installation lock, managed record or automated recovery.
- Use the verified existing private inode and local Linux bind mount, with
  matching host/container device, inode and UID. Remote daemons, UID remapping
  and filesystems that cannot preserve this flock contract are unsupported.
- Keep the context open through candidate validation and record commit. A
  candidate must not replace the lock inode, and external authenticated
  readiness is intentionally blocked during that scope. Full installer
  cutover still needs internal validation before admitting new writes.
- Stop/inspect failures can leave the exact old container stopped. The caller
  must inspect and recover that ID before choosing rollback. No credentials,
  workspace data, source releases or containers are automatically replaced.
- The host installer must survive. Its death releases its flock; an already
  dispatched Docker stop is not crash-atomic. This mechanism tolerates probe
  and exec-pipe loss while the host holder survives, and does not claim safety
  against arbitrary concurrent host/filesystem writers or independent Proxmox
  operations not represented in the backend's tracked attempts.

## Remaining integration

The installer is not deployment-ready. `main.yml`, parameter source/generated
JSON and README still use the previous obsolete installer contract. Remaining:

1. Managed installation record, serialized release staging, immutable
   runtime/template copies and image/profile checks; wire exact ownership and
   binding inspection into this record.
2. Authenticated unchanged-repeat no-op; existing credential digests and valid
   encryption key verification against existing database records.
3. Integrate the verified held-maintenance primitive into candidate migration,
   internal readiness validation and record cutover, with explicit rollback
   before accepting new writes.
4. Explicit stopped legacy-container mapping preserving original database,
   workspace paths, credentials and historical artifacts; unknown running
   legacy installations must remain untouched.
5. Main playbook/descriptor/README integration, public liveness and authenticated
   readiness/Proxmox registration, with protected input and no token logging.
6. Full disposable Docker and real Ansible installer acceptance for
   fresh/repeat/busy refusal, guarded update, failed migration preservation,
   wrong/missing key and runtime read-only mounts. The tests above verify the
   maintenance mechanism, not the whole installer.

Reference: Docker documents that `exec -i` keeps stdin open and exec processes
run only while the container primary process exists:
https://docs.docker.com/reference/cli/docker/container/exec/
Compose bind/read-only configuration:
https://docs.docker.com/reference/compose-file/services/


## Paused consumer TDD checkpoint — 2026-09-11

The user requested a stop to conserve usage. The existing helper implementation
at `490ec100675bf331ef7977853475944d428f1f26` remains unchanged. Its previously
recorded **51 passing tests** (including two real Docker cases) are helper
acceptance only; they were not rerun during this consumer planning slice.

Two new test files preserve the next consumer's behavior contract:

- `tests/test_backend_container_consumer.py`: invalid input before mutation,
  refusal to adopt unknown installation or historical workspace data,
  installation serialization without replacing the lock inode, symlink-lock
  refusal, byte/literal-link-preserving staging and special-file refusal.
- `tests/test_backend_container_consumer_docker.py`: proposed real Ansible bundle
  → disposable Docker fresh installation, unchanged authenticated repeat,
  retained database/workspace/credential bindings, changed-plan refusal and
  valid-but-wrong credential-key refusal. It first asserts the consumer is wired
  into `main.yml`; therefore the obsolete playbook cannot execute accidentally.

The initial focused TDD run produced **8 expected failures** in 0.16 seconds:
seven because `files/container_apply.py` is absent, and one because the real
bundle remains unwired. Log: `/tmp/r42-installer-consumer-red.log`. No Docker
container, guest, network, service, provider or installation was changed by this
run. These are intentionally red tests on the isolated installer branch, not a
passing release candidate. No new consumer implementation was started.

### Agreed next consumer slice

Use one standard-library CLI called from the real Ansible bundle, reusing
`container_plan.py`, `container_install.py` and `container_maintenance.py`.
Serialize changes with a private installation-root lock; keep a versioned,
atomically written managed record with the exact immutable image/container ID,
configuration, persistent mount bindings and credential digests. Stage runtime
and private template trees into a new immutable release, preserving literal
symlink strings and bytes; reject escaping links, unsupported paths and unknown
legacy state before provisioning or overwrite. Validate the candidate's actual
runtime profile and configured environment inside the image.

The first executable slice should support fresh installation and unchanged
repeat through `main.yml`, the parameter source/generated descriptor and README.
An unchanged repeat must inspect the exact running container, image, mounts,
release bytes, credentials and authenticated readiness without recreating it or
rewriting state. Existing records must retain the configured database/workspace,
API token, encryption key, runtime and template bindings. Test in a uniquely
named disposable local container via actual Ansible; do not run the existing
obsolete playbook merely to make these tests proceed.

A changed managed plan must never fall through to ordinary Compose replacement.
Until update integration is implemented, refuse it explicitly before stopping
or modifying the old container. The full installer objective still requires
held-admission candidate migration/validation/cutover, original credential
verification against encrypted database records, failure recovery and reviewed
rollback. Keep the existing `stopped_container(...)` context and original
admission inode held through validation and record commit. Unknown running
legacy installations must remain untouched; stopped legacy adoption requires
explicit mapping and its own acceptance.

Pending acceptance remains fresh/repeat execution, runtime/template immutable
mounts, busy update refusal, guarded update, failed migration preservation,
wrong/missing keys, recovery/rollback and explicit legacy adoption. The new tests
are the starting point for this work, not proof that it is implemented.

## Executable consumer continuation — 2026-09-11

The saved eight red tests were reproduced at `e075ea3` before implementation
(`/tmp/r42-installer-consumer-resumed-red.log`). The consumer is now called by
the real bundle. `main.yml`, descriptor source/generated JSON and README use
its authenticated immutable-image contract instead of source sync, post-start
migration, unauthenticated OpenAPI probes and implicit host-network changes.

Implemented in this continuation:

- Private serialized installation lock and versioned managed record. Exact
  image/container IDs, configuration, mount bindings, credentials and release
  bytes are checked before accepting an unchanged repeat.
- Fresh installation stages private runtime/template copies with literal link
  and byte preservation. It creates a stopped candidate, persists its full ID,
  then holds HTTP admission through startup, real internal readiness/profile
  checks and record commit.
- Explicit managed update uses the earlier continuous host-admission primitive,
  real installed idle audit and exact original container ID. Persistent paths,
  UID/GID and credentials cannot be relocated. Busy work refuses before stop.
- Updates preserve a consistent SQLite backup and old stopped container. Failed
  candidates are stopped before DB restoration and exact old-ID restart while
  admission stays fenced; successful cutover commits before admission resumes.
- `pending.json` blocks silent adoption of incomplete work. Legacy path aliases
  map explicitly, while unknown installations/historical data stay preserved and
  refused. No whole-SSH-home mount or implicit systemd conversion is introduced.

Actual Ansible → disposable Docker acceptance passed in 115.15s, handle71409,
log `/tmp/r42-installer-consumer-update-green2.log`: fresh install, authenticated
unchanged repeat, implicit changed-plan refusal, changed valid encryption-key
refusal, real provisioning-lock busy refusal without stopping the API, explicit
successful update retaining original admission inode/credentials/workspace, and
failed candidate rollback. The failure fixture modifies SQLite with its own
`failed_candidate` table and exits; that table is absent after restoration,
while the original managed record and running container ID are restored. The
first failure-fixture attempt stopped on the workstation's missing Docker
credential helper before its test image could build; the passing fixture uses
its own empty Docker configuration and a local build without registry pulls.

The actual runtime fixture also passed: handle54605, 10 checks with one other
Docker case deselected in 10.70s (`/tmp/r42-installer-runtime-green.log`). This
includes the consumer unit cases and a real generated `/runtime` profile,
read-only runtime/template mounts, rejected runtime writes (EROFS), exact literal
symlink retention, and refusal to treat edited source bytes as unchanged.
New regressions also established that a candidate cannot start before its ID is
recorded, and an unfinished pending cutover cannot become an unchanged repeat.
Final host/planner/credential/maintenance/consumer validation passed 61 tests in
0.71s (`/tmp/r42-installer-consumer-host-final.log`). Three additional red-to-green
planner cases refuse writable mount overlap with installation records or global
credentials. Scoped Ruff, descriptor regeneration and whitespace checks pass.

All disposable resources use the already reviewed local immutable image
`sha256:c025beb8c3bfd7299aa9addee69e9dfbae2515f88939344e06279f2cd72070c1`.
The intentionally failing image is derived locally and removed afterward.
Containers and networks are tracked by their unique installation label/full ID
and removed by fixtures. No PVE guest, shared systemd installation, provider,
firewall or upstream SDN state is touched.

The earlier “Remaining integration” and paused-TDD sections are historical
checkpoints. The current README is the authoritative public contract. Remaining
work is explicit offline legacy-container adoption, automatic fresh-failure or
interrupted-cutover recovery, configured provider/Proxmox seeding if desired,
retention/pruning, and matched image/release acceptance before live installation.
Host-installer/daemon death and independent external writers are not
crash-atomic; stop/inspection/backup failure can require exact-ID recovery.
This source checkpoint does not claim the entire historical installer objective
or a shared-systemd-to-container migration is complete.
