# r42topo — Scenario Authoring & Topology Compiler — Implementation Plan

> Status: **proposed** · Target repo: `range42-playbooks` · Branch: `feat/r42topo-scenario-authoring`
> Companion repos: `range42-catalog` (templates), `range42-backend-api` (FastAPI consumer)

## 1. Goal

A Python package, **`r42topo`**, living in `range42-playbooks`, that turns a declarative,
pydantic-validated **`topology.json`** into the Ansible artifacts a deploy needs, then hands
them to the existing backend runner. One **pure core**; thin frontends (Typer **CLI**,
Textual **TUI**, and an importable **API adapter** the FastAPI backend calls).

### Consumers of the core (drives the no-frontend-in-core rule)

`r42topo.core` / `r42topo.api` are framework-agnostic and imported by **three** independent
consumers — so the core must stay consumer-neutral (no FastAPI/Typer/Textual types in its
signatures; errors are the plain `TopologyError` hierarchy, not `HTTPException`/exit codes):

1. **range42-backend-api** (FastAPI) — authors/compiles, then runs `_universal`.
2. **r42topo's own CLI/TUI** (Typer + Textual).
3. **the range42 deployment CLI/TUI** — rewrite in progress; will import the same core
   instead of re-implementing scenario logic.

CLI/TUI dependencies are packaged as **extras** (`[cli]`, `[tui]`) so backend and deployment
consumers can install the core alone. Any shared interactive logic (validation messages,
"next free vm_id/IP", topology diff) lives in `core`/`api` so all three frontends reuse it.

It generalizes the hardcoded `05_network_isolation` (iptables FORWARD rules) from
`feat/demo_lab_network-scenario` into reusable, parametric **catalog templates**, and feeds the
`_universal` scenario stub from `feature/gamenet-authoring-v1`.

## 2. Locked decisions

| # | Decision |
|---|----------|
| 1 | Output = pydantic-validated `topology.json` (source of truth) **+ a compiler** that expands it into inventory, `scenario_vms.json`, network policy, stage wiring. |
| 2 | CLI = **Typer**, TUI = **Textual**, both thin over a shared **pydantic v2 pure core** (no Typer/Textual/FastAPI imports in `core/`). |
| 3 | Catalog gains **network/isolation policy templates** AND **box/topology templates** (new `05_topology_layer/`). |
| 4 | Must **match the backend contract**: scenario resolves at `scenarios/<name>/main.yml`, name regex `^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$` (no dots); API calls `run_playbook_core(playbook, inventory, extravars=…)`. |
| 5 | **Trust model = operator-only** (trusted-but-fallible). Authoring is behind an authenticated admin path; full validation still enforced, but the threat model does not assume end-user-supplied input. |
| 6 | **Format**: YAML for authored catalog templates; JSON for `topology.json` and all compiled artifacts (the latter cross the process boundary into `extravars`). |

| 7 | **Deploy path = `_universal` only** (rewrite-aligned). The compiler emits `topology.json` + artifacts + extravars; deployment runs via `_universal` Plan B, driven by the rewritten deployment CLI/TUI and the backend API. The compiler does **not** materialize a `scenarios/<name>/` dir, and today's `range42-context`/`range42-init.py` selector is **not** retrofitted (it is superseded by the rewrite). |

Defaults for still-open items (revisit before networked exposure):
- **Integration target**: the `_universal` playbook on `feature/gamenet-authoring-v1` (prerequisite for the P3 green slice; does not block P1–P2).
- **Backend wiring**: editable pip-install of the playbooks repo into the FastAPI venv (preferred over `PYTHONPATH`).

### Deployment boundaries (what r42topo is NOT)

r42topo **authors, validates, and compiles** — it produces *data*, never touches Proxmox.
The actual deploy (create VMs, apply the `R42-FORWARD` iptables policy, install catalog
roles/docker stacks onto each box) is done by **Ansible**. The catalog is consumed at two
distinct moments: **compile time** r42topo reads catalog *templates* (`box_templates`,
`network_policies`); **deploy time** Ansible pulls catalog *roles/stacks* (box `attachments`)
via `ANSIBLE_ROLES_PATH`.

Two prerequisites live **outside this module** and gate the first real Proxmox deploy:

1. **`_universal` Plan B** — `scenarios/_universal/main.yml` is currently a *stub* (asserts
   `topology.json` exists, no-ops). The real "load topology → create VMs → apply network →
   dispatch attachments" playbook must be implemented. Tracked as an external dependency.
2. **Deployment CLI/TUI rewrite** — today's `range42-init.py::list_deployable_scenarios`
   requires a `templates/` dir (4 files) and skips `_`-prefixed names (so `_universal` is
   excluded), and `range42-context deploy` runs `<scenario>.setup.sh` from a materialized
   scenario dir with no notion of `topology.json`/extravars. The rewrite teaches the
   topology→`_universal` flow; r42topo's importable core is what it will call.

P1–P4 (author/validate/compile/CLI) are fully testable **without** either prerequisite — the
P3 green slice runs against the existing `_universal` *stub* (asserts the compiled topology is
well-formed). End-to-end Proxmox deploy depends on Plan B landing.

## 3. Verified contract (from `range42-backend-api`)

- `run_playbook_core(playbook: Path, inventory: Path, limit, tags, cmdline, extravars: dict, quiet)` — single
  ansible-runner entry point; isolated `private_data_dir`; reads `ANSIBLE_ROLES_PATH` / `ANSIBLE_CONFIG` / vault env.
- `resolve_scenarios_playbook(name, "public_github")` → `<playbooks>/scenarios/<name>/main.yml`; name regex above; `_universal` is valid.
- `_universal/main.yml` consumes extravars: `r42_topology_path`, `r42_inventory_dir`, `r42_deployment_id`,
  `r42_attempt_id`, `r42_scope`, `r42_team_id`.
- Stack: FastAPI 0.115, **pydantic v2**, ansible-core 2.19.1, ansible-runner 2.4.1. Schemas use `{rc, result:[…]}`
  envelopes, fields `proxmox_node`, `vm_id` (str), `iface_bridge`, IP regex patterns.
- Path-traversal posture to reuse (`app/utils/checks_playbooks.py`): regex + `resolve(strict=True)` + `is_relative_to` + symlink rejection.

## 4. Data flow

```
operator ─┬─ Typer CLI  ─┐
          ├─ Textual TUI ─┼─► r42topo.core (pydantic, pure) ─► topology.json (source of truth)
          └─ FastAPI      ┘            │ compile_topology()
   ┌───────────────────────────────────────────────────────────────────────┐
   │ inventory/hosts.yml · manifest/scenario_vms.json ·                      │
   │ network_policy.json (ordered FORWARD rules) · stages.json · topology.json │
   └───────────────────────────────────────────────────────────────────────┘
                                       │ resolve_universal_extravars()
                                       ▼
   backend: run_playbook_core(scenarios/_universal/main.yml, hosts.yml, extravars={r42_*})
                                       ▼
            ansible-runner ─► Proxmox host (iptables R42-FORWARD chain + VM lifecycle, as root)
```

## 5. Package layout (`range42-playbooks/r42topo/`)

Flat top-level package (repo is otherwise pure Ansible). `setuptools` `include = ["r42topo*"]`
so build tooling never touches `scenarios/`/`bundles/`. Files kept < 400 lines.

```
r42topo/
  __init__.py
  core/                       # PURE — pydantic v2 + pyyaml + stdlib only
    constants.py              # SCENARIO_NAME_RE, IPV4/CIDR/bridge regexes, deny-list tokens, octet rule
    errors.py                 # TopologyError, ValidationError, CatalogNotFoundError, CompileError
    models.py                 # Topology → Subnet / Zone / Box / Attachment / NetworkPolicyRef
    catalog_models.py         # BoxTemplate, NetworkPolicyTemplate (symbolic), SubnetLayout
    catalog.py                # CatalogLoader: id@semver → validated template (+ recorded hash)
    idalloc.py                # vm_id/IP octet-rule + _reserved.json uniqueness (atomic, locked)
    io.py                     # load/dump topology, atomic write, sorted JSON/YAML
    compiler/
      __init__.py             # compile_topology() → CompileResult
      inventory.py            # → hosts.yml (nested groups; force_valid_group_names=never safe)
      scenario_vms.py         # → manifest/scenario_vms.json (demo_lab shape)
      network_policy.py       # → ordered FORWARD rule table (weight bands) + segmentation linter
      stages.py               # → per-zone box/attachment dispatch list for _universal Plan B
    extravars.py              # resolve_universal_extravars() → {r42_*} (typed allow-list)
  api.py                      # load_catalog / author_topology / validate_topology / compile_topology / resolve_universal_extravars
  cli.py                      # Typer: author / validate / compile / show
  tui/
    app.py  widgets.py        # Textual, thin over core
pyproject.toml                # core deps unconditional; [cli]/[tui]/[dev] extras
tests/                        # golden-file compiler + schema/idalloc/security tests
docs/r42topo-plan.md          # this document
```

**Importable API (pure — backend imports this):**

```python
load_catalog(catalog_root: Path) -> Catalog
author_topology(spec: dict, *, catalog: Catalog) -> Topology
validate_topology(t: Topology, *, catalog: Catalog, reserved: ReservedIndex) -> list[str]
compile_topology(t: Topology, *, workspace: Path, catalog: Catalog, reserved: ReservedIndex) -> CompileResult
resolve_universal_extravars(result: CompileResult, *, deployment_id, attempt_id, scope, team_id=None) -> dict
```

## 6. topology.json schema (pydantic v2, `extra="forbid"`)

```
Topology(schema_version:int=1, scenario:str[regex,no-dots], description:str, proxmox_node:str,
         subnets:[Subnet], zones:[Zone], boxes:[Box], network_policy:NetworkPolicyRef)
Subnet(name, cidr[CIDR], bridge[^vmbr\d+$], gateway?:IPv4)
Zone(name, subnet→Subnet.name, role:Literal[admin|ctf|team|student|template])
Box(vm_name[^[a-z0-9-]+$], vm_id:int[1000..9999], ip:IPv4, zone→Zone.name,
    box_template→catalog id, inventory_group[^[a-z0-9_]+$], attachments:[Attachment])
Attachment(kind:Literal[role|container|gamification], catalog_ref:str[dots allowed], params:dict)
NetworkPolicyRef(template→catalog id@semver-range, overrides:dict)
```

Note: `scenario` is dot-free (backend rule); `Attachment.catalog_ref` **allows dots** (role naming
`software.install.wazuh`) — different fields, different regexes.

## 7. Catalog templates (`range42-catalog/05_topology_layer/`)

Templates carry **symbolic structure only — zero concrete IPs/CIDRs/bridges**; the topology binds
symbols to concrete values. Directory-per-version; `id@semver-range` references; resolved exact
version + content hash recorded into compiled output (lockfile pattern). Three independent version
axes: catalog-repo version · template SemVer · policy-schema `api_version`. `manifest.json` gains a
`topology` layer entry.

```
05_topology_layer/
  network_policies/air-gap-ctf/v1.0.0/template.yml   # symbolic zones + allow/deny matrix + airgap + wazuh exceptions
  box_templates/{admin-wazuh,deployer,vuln-box,student-box}/v1.0.0/template.yml
  subnet_layouts/default-3zone/v1.0.0/template.yml
```

### Network model (the core generalization)

Three layers: **Policy template (intent, symbolic)** → **Topology binding (concrete)** →
**Compiled rule table (execution)**.

- Template declares symbolic `zones`, `services` (e.g. `siem`), a **sparse allow/deny matrix**,
  and `airgap_zones`. The author writes only exceptions; `default_action: drop` + `allow_intra_zone`
  cover the rest. Scales to n zones with no schema change.
- Topology supplies `zone_bindings` (zone → CIDR + bridge + optional VLAN) and `service_bindings`
  (siem → wazuh IP). **The hardcoded wazuh IP disappears from the playbook.**
- Compiler emits a **deterministically ordered** rule table via fixed **weight bands**
  (`ESTABLISHED,RELATED` → service-ACCEPT → zone-ACCEPT → intra-zone → zone-DROP → air-gap →
  default-deny), stable-sorted → byte-reproducible. Order is *correctness* (iptables is
  first-match-wins) and is decided in the testable compiler, never at Ansible runtime.
- The generalized `proxmox_forward_rules.yml` becomes a **data-driven loop** that
  **flush-and-rebuilds a dedicated `R42-FORWARD` chain** (not the live `FORWARD`), then ensures a
  single jump into it — naturally idempotent, order-exact, and cannot lock out host SSH (FORWARD-only).
- Edge cases: reject two zones on the same bridge with non-disjoint subnets (CIDR ambiguity);
  optional `match_mode: cidr|iface|both` for CIDR reuse across labs.

## 8. Source-of-truth hierarchy

`_reserved.json` (what's allowed/forbidden: reserved subnets, vm_id bands, service IPs)
→ `topology.json` (what this scenario binds)
→ `scenario_vms.json` (concrete per-VM: vm_id↔ip↔bridge↔role)
→ compiled artifacts (derived, never hand-edited).
Catalog templates sit orthogonal as reusable symbolic intent. The compiler **cross-validates**:
every box IP must fall in exactly one bound zone subnet; bridges must match.

**Octet rule** (`vm_id % 1000 == ip last octet`): enforced as an **error for newly authored boxes**,
**warning for legacy `_reserved.json` rows** (existing `demo_lab_network` data violates it: `4000 → .170`).

## 9. Security requirements (operator-only model; baked into phases)

- **Structured emit only** (`yaml.safe_dump` / `json.dump`) — never interpolate topology strings into
  templates → no SSTI. Deny-list rejects fields containing `{{ }}`, `{% %}`, `${`, backtick, `;`, `|`,
  `&`, newline, null byte, `..`, leading `-`, absolute paths.
- **iptables fields as typed argv/rule-data**, never shell concatenation: strict CIDR
  (`ip_network(strict=True)`), ports 1–65535, bridge `^vmbr\d+$`, action ∈ {ACCEPT,DROP,REJECT}.
- **Segmentation linter** post-compile (fail closed): ESTABLISHED-ACCEPT precedes any DROP;
  no `ctf → admin`; air-gap intact; default-deny last; **Proxmox mgmt SSH never blocked**.
- **Atomic, locked reservation** vs `_reserved.json` (TOCTOU-safe); reject cross-scenario / admin /
  template-band vm_id/IP claims.
- **Path posture** (`resolve(strict=True)` + `is_relative_to` + regex + symlink rejection) for template
  ids and every compiler read/write path.
- **extravars = typed allow-list** (strip any `ansible_*`/`ANSIBLE_*`); **no secrets** in any emitted
  artifact (vault stays the only secret source; generated artifacts on gitignored paths).
- Honor `force_valid_group_names=never`: validate host `^r42\.[a-z0-9-]+$` / group `^[a-z0-9_]+$` names.
- **Fail-closed compile**: build in temp, validate fully (incl. linter), atomic-rename; never run on a
  partially-validated artifact. Size/count caps to prevent compile-time DoS.

## 10. Packaging

```toml
[build-system] requires = ["setuptools>=68"] build-backend = "setuptools.build_meta"
[project] name="r42topo" version="0.1.0" requires-python=">=3.11"
          dependencies=["pydantic>=2,<3","pyyaml>=6"]
[project.optional-dependencies] cli=["typer>=0.12"] tui=["textual>=0.60"] dev=["pytest>=8.3","pytest-cov"]
[project.scripts] r42topo="r42topo.cli:app"
[tool.setuptools.packages.find] include=["r42topo*"]
[tool.pytest.ini_options] testpaths=["tests"]
```

`typer`/`textual` are **extras** so the backend installs core only (keeps the no-frontend-in-core
boundary at the dependency level too). `.gitignore` gains `__pycache__/`, `*.egg-info/`,
`.pytest_cache/`, `dist/`, workspace output dirs.

## 11. Build order (TDD — RED first; each phase independently testable)

| Phase | Delivers | Test gate |
|------|----------|-----------|
| **P1 Foundation** | `pyproject.toml`, `core/{constants,errors,models,io}.py`, `__init__.py`, `.gitignore` | topology round-trip + schema + deny-list unit tests |
| **P2 Catalog + idalloc** | `05_topology_layer/*` templates + `manifest.json` change; `catalog{,_models}.py`, `idalloc.py` | ref resolution, octet rule, locked uniqueness vs `_reserved.json` |
| **P3 Compiler + adapter** ◄ first end-to-end slice | `compiler/*`, `extravars.py`, `api.py`, segmentation linter | author→compile→`_universal` stub runs **green**; golden-file inventory/rules; security-linter tests |
| **P4 CLI** | `cli.py` (Typer) | `typer.testing.CliRunner` |
| **P5 TUI** | `tui/*` (Textual) | Textual pilot tests |
| **P6 Docs** | module README + catalog README + backend integration note | — |

Dependency: P1 → P2 → P3 → {P4, P5 parallel} → P6. **Demoable milestone = end of P3.**
Coverage target ≥ 80% (project rule).

## 12. Prerequisites / risks

1. `_universal/main.yml` is on `feature/gamenet-authoring-v1`, not `main` — needed for the P3 green slice.
2. `r42topo` must be importable from the FastAPI venv (editable pip-install recommended).
3. Octet-rule conflict with legacy `_reserved.json` data — enforce on new boxes only.
4. Resolver drift between CLI and backend — single packaged core, version-pinned, shared golden tests.
5. Stale on-disk catalog clone — loader records resolved version + hash; surface mismatch.
