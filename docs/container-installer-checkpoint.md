# Container installer checkpoint — incomplete, paused 2026-09-11

Worktree: `/tmp/r42-container-installer-next-wave`, branch
`fix/backend-container-installer-20260911`, based on playbooks `a150867`.
Earlier credential-only checkpoint: `22e045d`. The root handoff remains
`_local-specs/2026-09-11-container-installer-handoff.md` in the shared project root.

## Saved tested slice

`files/container_plan.py` now validates an explicit installation configuration
and renders the authenticated Compose contract without creating state. It
requires an immutable image ID/digest, checks explicit host/container paths,
retains configured legacy workspace/database locations, uses token/key file
mounts, and supplies complete runtime/template mounts and environment when
configured. It does not mount the operator's SSH home. Tests first reproduced
14 failures for the missing planner, then passed all 14 new cases plus the 7
existing credential cases. Focused Ruff checks pass after formatting cleanup.

Logs: `/tmp/r42-container-plan-red.log` and
`/tmp/r42-container-plan-green.log`. Only the planner and descriptor-independent
Compose renderer are implemented. They are not yet called by the bundle.

## Pending test specifications

`tests/pending/backend_container_maintenance.py.txt` contains the next tests.
They failed for the expected missing `container_maintenance.py` implementation
before the user requested a stop. The file is deliberately outside pytest
collection. On resumption, move it into the active tests directory, observe the
red result, then implement the held helper and host admission context managers.
The initial red log is `/tmp/r42-installer-maintenance-red.log`.

## Remaining integration

The installer is not deployment-ready. `main.yml`, parameter source/generated
JSON and README still use the previous obsolete installer contract. Remaining:

1. Managed installation record, ownership/binding/image inspection, serialized
   release staging, immutable runtime/template copies and image/profile checks.
2. Authenticated unchanged-repeat no-op; existing credential digests and valid
   encryption key verification against existing database records.
3. Held `docker exec -i ... maintenance_guard` through stop of the exact owned
   container ID; no one-shot stdin pipe. Cover refusal and subprocess failure.
4. Candidate migration/admission/readiness cutover and rollback before accepting
   new writes. Proposed approach: acquire the same persistent host admission
   flock after the old container stops and hold it through candidate validation
   and record commit; validate readiness internally while external finite HTTP
   remains blocked. This design is not implemented or accepted by Docker tests.
5. Explicit stopped legacy-container mapping preserving original database,
   workspace paths, credentials and historical artifacts; unknown running
   legacy installations must remain untouched.
6. Main playbook/descriptor/README integration, public liveness and authenticated
   readiness/Proxmox registration, with protected input and no token logging.
7. Disposable Docker and real Ansible acceptance for fresh/repeat/busy refusal,
   guarded update, failed migration preservation, wrong/missing key and runtime
   read-only mounts. Planner boundary cases and final ownership checks still
   need review before integration.

No Docker containers were started, stopped or changed in this resumption. No
PVE, shared systemd service, provider, runtime pin or upstream SDN changes were
made. Existing Docker images include the separately tested maintenance images;
use immutable IDs and uniquely named disposable resources when resuming.

References checked: Docker documents that `exec -i` keeps stdin open and exec
processes run only while the container primary process exists:
https://docs.docker.com/reference/cli/docker/container/exec/
Compose bind/read-only configuration:
https://docs.docker.com/reference/compose-file/services/
