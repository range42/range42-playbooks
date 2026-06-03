# r42topo convergence — backend engine port map (Phases 4–5)

> Source: `code-explorer` over `range42-backend-api@feature/gamenet-authoring-v1`. Drives
> Phases 4–5 of the convergence (issue #67). Pairs with `docs/r42topo-convergence-plan.md`.

## Port order (PURE → `r42topo.core`)

```
Step 1  vmid_guard.py        stdlib only; foundational (allocation + preflight depend on it)
          → DEFAULT_PROTECTED_RANGES, VmidProtectedError, assert_vmid_safe, filter_safe_vmids
Step 2  allocation.py        PURE SUBSET only
          → allocate_vmids(*, start, count, reserved, host_overrides) -> list[int]
          → DEFER: allocate_vmids_locked (module asyncio.Lock), ssh_controlmaster_env (mkdir)
Step 3  preflight.py         PURE/SYNC/NO-IO SUBSET only
          → PreflightCheck, PreflightReport, check_vmids, check_resource_budget,
            check_secret_completeness, check_topology_node_role, check_vmid_safety_for_topology
          → DEFER: check_topology_assets (FS), check_proxmox_api_status / check_sdn_bridge /
            check_docker_image_pull / check_git_reachable (httpx), run_declarative_checks
Step 4  inventory_writer.py  standalone (yaml + pathlib); gated by topology/*.json vectors
          → write_inventory(*, topology, team_count, codename, proxmox_address,
                            ssh_keys_dir, dest) -> Path
```

Dependency edges (pure set): `vmid_guard ← allocation.allocate_vmids`, `vmid_guard ← preflight`,
`inventory_writer` is an isolated leaf.

Acceptance: `inventory_writer` golden-compared to the backend's `write_inventory` output on
`topology/01-minimal.json` + `02-multi-team.json` (generate golden from `/tmp` clone of the
backend at port time). `vmid_guard`/`allocation`/`preflight` mirror the backend unit tests
(`tests/core/test_vmid_guard.py`, `test_allocation.py`, `test_preflight*.py`).

## DEFERRED — redaction / resolve_secrets

Not ported (vector divergence — see convergence-plan deferral note): backend
`redaction.VAULT_MARKER = "__range42_vault_origin__"` vs vector `__vault_tagged__`; token
`[REDACTED:vault_tagged]` vs vector `***REDACTED***`; vectors want a pure
`apply_redactions(event, layers) -> {event, redactions[]}` but backend `run_pipeline` returns
only the event and writes an audit file. Reconcile the marker/token/return-shape with the spec
owner before porting. The four layer *classes* are pure and portable once the contract is fixed.

## IMPURE — must NOT enter r42topo core (future r42runtime)

| Item | Why |
|---|---|
| `core/models.py` | SQLAlchemy ORM (DB tables) |
| `core/workspace.py` | imports `config.settings` at module load; mkdir/subprocess/`/proc/mounts`/fsync |
| `core/project.py` | `subprocess` git clone; fs writes |
| `core/runner_protocol.py`, `runner_detached.py` | ansible-runner subprocess interface; asyncio subprocess + fs |
| `core/deploy_trigger.py` | full orchestrator: AsyncSession + runner + all subsystems |
| `allocation.allocate_vmids_locked` | module-global `asyncio.Lock` (loop-bound) |
| `allocation.ssh_controlmaster_env` | creates `~/.ssh/range42/` |
| `redaction.RedactionAuditWriter`, `run_pipeline` | appends JSONL audit file |
| `preflight.check_topology_assets` + network checks | filesystem / `httpx` |

## Tricky couplings (port hazards)

- **`app/core/errors.py` imports FastAPI/Starlette at module load.** `project.py`/`runner_detached.py`
  import `ProjectCheckoutError`/`RunnerSetupError` from it. → In r42topo define plain `Exception`
  subclasses; never `from app.core.errors import …`. Keep HTTP-envelope wiring in the backend.
- **`workspace.py` reads env-backed `settings` at import** → don't import it in a pure context (it's
  r42runtime anyway).
- **`allocation._ALLOC_LOCK = asyncio.Lock()` at module import** is event-loop-bound → port only the
  pure `allocate_vmids`; keep the locked variant in r42runtime.
- **`VAULT_MARKER` links `redaction` ↔ `resolve_secrets`** and mismatches the vectors → reconcile first.
- **`preflight.check_topology_assets` is `async` but does sync FS calls** → in r42runtime run it in a
  thread executor.
