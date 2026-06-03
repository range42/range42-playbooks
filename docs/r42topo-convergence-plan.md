# r42topo Convergence — align to the canonical Range42 schema & become the shared engine

> **Tracking issue:** range42/range42-playbooks#67
> Status: **proposal — needs cross-team sign-off** (the schema + engine are owned by an active
> effort; see §8). Supersedes parts of `r42topo-plan.md` and `range42/docs/r42deploy-plan.md`.
>
> Progress (branch `feat/r42topo-canonical-schema`): **Phase 1 schema intake**, **Phase 2
> `expand_replication`**, **Phase 3 `compose`** — done & pushed, all green against the shared
> vectors. **Phases 4–5** — done & pushed: ported `vmid_guard` → `allocation.allocate_vmids`
> (pure subset) → `preflight` (sync/no-IO subset) → `inventory_writer` into `r42topo/core/` as
> framework-free pure modules (plain `Exception` subclasses; no FastAPI/httpx/asyncio).
> `inventory_writer` is golden byte-compared to the backend's `write_inventory` over the shared
> topology vectors (`tests/golden/inventory/`); the rest mirror the backend unit tests. Impure
> bits deferred to r42runtime per `docs/r42topo-port-map.md` (`allocate_vmids_locked`,
> `ssh_controlmaster_env`, FS/httpx preflight checks, `run_declarative_checks`).
> **Phase 7 (backend swap) held for @pparage sign-off** per §8.
>
> **Deferred — redaction/resolve_secrets**: the backend `app/core/redaction.py` (`run_pipeline`,
> impure audit-file writer) **diverges from the shared redaction vectors** — marker
> `__range42_vault_origin__` vs vector `__vault_tagged__`; token `[REDACTED:vault_tagged]` vs
> vector `***REDACTED***`; vectors expect a pure `apply_redactions(event, layers) -> {event,
> redactions[]}` while the backend returns only the event (and vector 02 is `edge`). The
> contract is unsettled, so this operator is **not ported** until reconciled with the spec owner
> (don't invent it). `serialize/*` vectors are the UI canvas→doc step (TS-side) — no Python op.

## 0. Why this exists

While planning the deployment CLI/TUI rewrite we discovered the topology/`_universal`
architecture **already exists** and is more mature than the `r42topo` model we built — and it
has a **canonical, code-generated JSON Schema** that is the real contract. `r42topo` (built by
generalizing `demo_lab_network`) diverges from it. Decision taken: **converge on one shared
topology engine that conforms to the canonical schema**, and have `r42topo` become that engine
(replacing the backend's `inventory_writer.py` et al.) — rather than maintain two divergent
designs.

## 1. The canonical contract (source of truth)

Owned by **`range42-deployer-ui`**:
- `schema/range42.schema.json` — **Range42 Scenario Schema v1** (JSON Schema Draft 2020-12).
  `bundled.json` is the refs-resolved, generated form (do not edit).
- Generators: `tools/bundle-refs.sh`, `tools/generate-pydantic.sh` (→ `datamodel-codegen`).
- **Shared test-vectors**: `schema/test-vectors/{topology,compose,expand_replication,serialize,redaction}/`.
- Governing spec: `docs/specs/2026-04-14-deployer-ui-feature-design.md` (the "§10.3 / §21" issues cite).
- Consumers today: backend-api (`app/schemas/generated.py` via datamodel-codegen) and the UI
  (`src/types/range42-schema.ts`, `useTopologyResolver.ts`, `topologyRules.js`).

**Schema shape** (`$defs`): `SchemaVersion, Replication, AttachmentSource, Attachment, EnvVar,
Flag, NetworkAttachment, Node, Execution, CatalogEntry, ProjectOverlay, Attempt,
DeploymentRecord, EventLogEntry, PreflightCheck, PreflightRecord, ProxmoxHostHealth, ProxmoxHost`.

Topology doc top-level: `schema_version` ("1.0"), `kind` ("gamenet"), `name`, `naming_prefix`,
`bridge_base`, `preflight_checks[]`, **`nodes[]`** — a unified array discriminated by `kind`:
- `kind ∈ {vm, lxc, docker, network, router, firewall, skin, group}`
- `role ∈ {admin, team, trainee, shared}` (→ inventory groups `r42_admin` / `r42_blank_group`)
- `replication: {scope: shared | per_team}` (multi-team is first-class)
- network nodes: `cidr_template`/`bridge_template` = `"…{{ bridge_base + team_id }}…"`, `vlan_tag`
- vm/lxc: `template_vmid` (clone source), `config{cores,memory,…}`
- `attachments[]`: `{source:{kind:catalog_role, ref}, stage, vars}`, `networks[]`, `children[]`

## 2. The existing engine (range42-backend-api @ `feature/gamenet-authoring-v1`)

Already implemented in Python, **not yet merged to `dev`**:
- `app/schemas/generated.py` — pydantic models generated from `bundled.json`
- `app/core/inventory_writer.py` — nodes[] → Ansible `hosts.yml` (role→group, ssh keys/users)
- `app/overlay/expand_replication.py` — shared/per-team expansion (the overlay)
- `app/core/allocation.py` + `vmid_guard.py` — IP/VMID derivation + safety
- `app/core/preflight.py` — v1 topology checks (assets, VMID safety, node-role)
- `app/core/project.py` — project repo checkout at pinned SHA
- `app/core/workspace.py`, `runner_protocol.py`, `runner_detached.py`, `vault.py`, `locks.py`
- `app/routes/v1/projects/{crud,compose}.py` — compose/validate (effective_doc + hash)
- Tracking issues: backend #68 (done), #70, #73, #74, #82, #83; deployer-ui #58, #61.

## 3. Decision

**One shared topology engine, conforming to `range42.schema.json`, validated by the shared
test-vectors.** `r42topo` is realigned to BE that engine; the backend drops its in-repo
`inventory_writer.py` / `allocation.py` / `vmid_guard.py` / `preflight.py` / `expand_replication.py`
and imports `r42topo` instead. The deployer-ui remains the **schema owner**.

(Mechanically "r42topo becomes the engine" = r42topo absorbs the backend engine's logic under the
canonical schema. The schema + test-vectors are the authority; the package name is secondary.)

## 4. What changes in `r42topo`

**Replace the invented schema with the canonical one.**
- Drop the hand-written `Topology(subnets/zones/boxes, network_policy)` model.
- **Generate** the pydantic models from `range42.schema.json` via `datamodel-codegen` (reuse the
  deployer-ui `generate-pydantic.sh` pipeline), vendoring the schema (git submodule, or a copied
  `schema/` + a CI check that it matches the deployer-ui source). No hand-maintained schema.
- Re-implement the engine over the canonical doc, ported from the backend modules:
  - `expand_replication` (shared/per_team overlay) — port from `app/overlay/expand_replication.py`
  - `inventory_writer` (nodes→hosts.yml) — port from `app/core/inventory_writer.py`
  - `allocation` + `vmid_guard` (per-team VMID/IP derivation, `bridge_base + team_id`)
  - `preflight` (topology checks) — port from `app/core/preflight.py`
  - `compose`/effective_doc + hash — port from `routes/v1/projects/compose.py`
- **Validate against the shared test-vectors** (compose, expand_replication, serialize, topology)
  so `r42topo` is byte-compatible with what backend + UI expect. These vectors are the acceptance
  tests for the convergence.

**What survives from the `r42topo` we built** (carries over, not wasted):
- The **pure, framework-neutral core** discipline + `r42topo.api` adapter shape.
- The **security posture** (deny-list on free-text/attachment vars, `resolve(strict=True)` +
  `is_relative_to` path checks, structured `yaml.safe_dump`/`json` emit, fail-closed) — apply it
  to the canonical doc + project-repo checkout.
- **Deterministic, atomic emit** + the test-first rigor + golden-file approach.
- The **Typer CLI / Textual TUI** shells (re-pointed at the canonical doc + compose).
- The **catalog-template idea** maps onto canonical `CatalogEntry` / archetypes + the
  attachment `source:{kind:catalog_role, ref}` model — reconcile, don't reinvent.

**What is dropped / reworked:**
- `subnets`/`zones`/`boxes`, the **octet rule** (replaced by derived per-team VMID math +
  `vmid_guard`), and the **`network_policy` iptables-FORWARD generalization** (gamenet models
  networking via `network`/`firewall` nodes provisioned Proxmox-side; the air-gap/isolation
  becomes a `firewall` node or attachment — track against backend #83 firewall provisioning).
- The `05_topology_layer/` catalog templates we added — re-evaluate against `CatalogEntry`;
  likely superseded.

## 5. What changes elsewhere

- **range42-backend-api**: replace the five in-repo engine modules with `import r42topo`; keep
  `runner_detached`/`runner_protocol`/`db`/routes. Gate with the shared test-vectors so behavior
  is identical. (This is the `inventory_writer.py` replacement the decision calls for.)
- **range42-deployer-ui**: unchanged ownership of `range42.schema.json`; it stays the schema
  source. `r42topo` consumes it.
- **r42deploy** (the CLI/TUI rewrite): unchanged intent, but now imports the *converged* `r42topo`
  + the runner; the `r42runtime` extraction still applies for the impure run/workspace/vault layer
  (much of which already exists as backend `workspace.py`/`runner_detached.py` — port from there).

## 6. Build / convergence order

1. **Schema intake**: vendor `range42.schema.json` into `r42topo`; wire `generate-pydantic.sh`;
   generate models; round-trip the `topology` test-vectors. (Gate: fixtures parse.)
2. **expand_replication**: port + pass the `expand_replication` test-vectors.
3. **compose/effective_doc + hash**: port + pass the `compose` + `serialize` vectors.
4. **inventory_writer**: port nodes→hosts.yml + golden-compare to the backend's output.
5. **allocation + vmid_guard + preflight**: port + their tests.
6. **Security + emit hardening** re-applied to the canonical path (deny-list on `config`/`vars`,
   project-repo checkout path posture, atomic writes).
7. **Backend swap**: backend imports `r42topo`; delete its duplicated modules; shared-vector CI.
8. **r42deploy / r42runtime**: resume the deployment-tool plan on the converged base.

## 7. Open questions for the schema/spec owner

- Does the air-gap / inter-zone isolation from `demo_lab_network` become a `firewall` node, an
  attachment, or stay a scenario concern? (relates to backend #83)
- Where does `r42topo` physically live given it's now imported by backend + UI-tools + r42deploy —
  stay in range42-playbooks, or move? (revisits the earlier location decision)
- Schema vendoring mechanism into `r42topo`: git submodule of deployer-ui `schema/`, or
  copy-with-CI-drift-check?

## 8. ⚠️ Coordination gate (must-read)

This convergence **supersedes an active feature branch** (`range42-backend-api
@ feature/gamenet-authoring-v1`, author `pparage`) and **touches three repos** (deployer-ui
schema, backend engine, r42topo). It also **reworks much of the `r42topo` we just built**. It must
be agreed with the gamenet spec/branch owner (NC3) before execution — this is not a unilateral
change. The safe first step is a shared-test-vector contract: whatever package owns the engine
must pass `deployer-ui/schema/test-vectors/*`, which lets `r42topo` and the backend converge
without a flag-day.
