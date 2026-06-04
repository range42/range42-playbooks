# Session handoff — r42playbooks generator

**Date:** 2026-06-04. **Continue:** next session on a **different PC** → everything
below is **pushed** (both repos), don't rely on local-only state or `.claude` memory.

## Repos & branches
| repo | branch | resume with |
|---|---|---|
| `range42-playbooks` | `feat/r42playbooks-generator` | `git fetch && git checkout feat/r42playbooks-generator` |
| `range42-catalog` | `feat/topology-layer-templates` | `git fetch && git checkout feat/topology-layer-templates` |

Setup: `cd range42-playbooks && python3 -m venv .venv && .venv/bin/pip install -e ".[dev,cli,tui]"`
then `.venv/bin/python -m pytest -q` → **188 green**.

Generator entry point:
```
.venv/bin/python -m r42playbooks.cli new my_lab \
  --subnet default-3zone --box vuln-box:count=3 \
  --catalog ../range42-catalog -o scenarios/
r42playbooks-tui ../range42-catalog        # TUI (mouse + clavier, pas de raccourcis perso)
```

## What changed THIS session (beyond the original S1–S9 plan in r42playbooks-plan.md)
The plan's S1–S9 is done; then we refined the model substantially:

1. **Versioned image model** — `BoxTemplate.os` → **`image`** (`<distro>_<codename>`:
   `ubuntu_noble`, `debian_trixie`). `select_template`/`TEMPLATE_TABLE`/manifest/README/
   `show` all keyed by image. No `debian_forky` yet (Debian 14 is testing).
2. **Staged `01_init_proxmox`** (mirrors `_init_lab`): `stage_00-download_cloudinit_files/`
   + `stage_01-create_templates/templates/<image>/`, **image-selective** (a lab carries
   only the image sets it uses). Vendored with the **richer** content (idempotence guards
   + apt-proxy + manifest-driven `_update_templates`), path-fixed to the deeper nesting.
   Debian trixie image set added (9321/9331).
3. **`network_policy` removed from the generator path** — optional + ignored (isolation =
   per-box firewall roles, not a compiled policy). Kept in the spec for the parked engine.
4. **Attachment params → `stage_01`** — the renderer now emits ONE PLAY PER ATTACHMENT
   with its params as vars. All box_templates carry their `firewall_rules` (host firewall);
   `vuln-box` also wires a docker CTF stack (container attachment → docker-compose play).

## Architecture decisions LOCKED (don't re-litigate)
- **Model A**: `r42playbooks` is the **parametric generator** — it ALLOCATES vm_id/ip/subnet
  (octet rule, `_reserved.json`), picks the clone image from `spec+image`. (We considered
  moving network binding to r42deploy = Model B, and chose to KEEP it in the generator.)
- **`05_topology_layer` stays** but justified per sub-layer: `box_templates` ✅ (archetypes,
  core), `subnet_layouts` ✅ (placement), `network_policies` ❌ inert in the generator
  (parked-engine only, issue #67).
- **`box_template` = the parametric source of truth** for a VM's config (role/spec/image +
  attachment params: firewall_rules, docker).
- **Dependency direction (hard rule): `playbooks → catalog`, never the reverse.** Playbooks
  reference catalog roles by name; the catalog must NOT depend on the playbooks repo.
- **Both bundle families are candidates for DEPRECATION** (the catalog + generator supersede them):
  - `bundles/core/proxmox/.../create-vms-*` = byte-for-byte copies of demo_lab sections →
    fully replaced by the generator. **Dead.**
  - `bundles/core/linux/<os>/...` = role-invocation examples. They **cannot** become the
    reusable "recipe library" referenced by `box_templates` — that would invert the
    dependency (catalog → playbooks). Their only residual value is a **dev/test harness**
    (`test.sh` to apply one role to one VM) + examples; risk of becoming stale duplication.
- **If reusable role-config recipes/profiles are ever wanted** (the DRY answer to repeated
  attachment params), they live **IN THE CATALOG** (e.g. a `05_topology_layer/role_profiles/`
  layer or role defaults), referenced by `box_templates` — NOT in `bundles/`. This keeps the
  `playbooks → catalog` direction intact.

## Known architecture debt — base images belong in the catalog (`01_image_layer`)

The ONE ingredient referenced by the catalog that does NOT live in the catalog is
the **base VM image** (`image: ubuntu_noble` / `debian_trixie`). Its definition lives
in the **playbooks**: the `01_init_proxmox/.../templates/<image>/` creation playbooks
+ `r42playbooks/core/templates_table.py` (`TEMPLATE_TABLE`). Roles (`02_ansible_layer`),
containers (`03_container_layer`), subnet layouts (`05_topology_layer`) are all
catalog-owned; the image is not → a soft dependency-direction smell (the catalog box
"points up" toward the playbooks for that one ingredient).

**Fix (clean, respects the numbering):** move the VM base images into a NEW catalog
layer **`01_image_layer/`** (or `01_base_images/`). The catalog's numbered layers go
**foundational → composed**:
```
01 image_layer      ← ubuntu_noble, debian_trixie (VM)   ← the foundation (currently EMPTY slot)
02 ansible_layer    ← roles
03 container_layer  ← docker + lxc (CONTAINERS — NOT VMs)
04 gamification_layer
05 topology_layer   ← box_template references image(01) + roles(02) + containers(03)
```
- `01` is currently **empty** in the catalog — and it's exactly the most foundational
  slot. Mirrors the scenario section `01_init_proxmox` (runs first). Putting base images
  there **respects** the hierarchy, it doesn't break it.
- **NOT `03_container_layer`**: a VM (QEMU/KVM, own kernel, cloud-init boot — `vm_create`)
  is **not** a container. `03` is docker app-stacks + LXC system containers.
- **LXC base templates** (if LXC boxes are ever supported) are containers → they can stay
  in `03_container_layer/lxc/`, or `01` could become "all base images (vm + lxc)" — a
  secondary call.
- After the move: the catalog owns ALL ingredients (image/roles/containers/topology), the
  generator only *references* them, and `playbooks → catalog` holds with no exception.

(Not urgent — the current name-contract works and is validated. Do it when consolidating.)

## NEXT STEPS (priority order)
1. ⭐ **Validate on a real Proxmox** (`range42-context deploy` of a generated ubuntu + a
   debian_trixie lab). The Debian template-creation playbooks were ported from ubuntu but
   **never run against live Proxmox** — verify before trusting.
2. **Deprecate the bundles** once (1) confirms the generated trees deploy:
   `create-vms-*` (dead — generator replaces them) and `core/linux/*` (superseded; keep only
   if used as a dev/test harness). Add an "obsolete — generated by r42playbooks from the
   catalog" README rather than relying on them.
3. **Step 0 housekeeping**: close issue #67 (note: GitHub MCP is read-only, gh CLI absent →
   the user must run it), open the tracking issue.
4. (deferred) reusable role-config **profiles** — the DRY answer to repeated attachment
   params. **Lives in the CATALOG** (e.g. `05_topology_layer/role_profiles/`), referenced by
   `box_templates` by name — NOT in `bundles/` (would invert `playbooks → catalog`). Do this
   only if/when ≥2 boxes share the same params; for now inline params is the chosen approach.

## Notes / gotchas
- Untracked throwaway scenarios in `scenarios/` (`my_lab`, `test*`) — generated test output,
  not part of any commit. `my_lab` exists in early-commit *history* blobs (untracked in the
  final tree); harmless, scrub history only if a clean push is required.
- Catalog is a separate gitignored sibling repo; tests use a `fake_catalog` fixture, never
  the real path.
- Key files: `core/render.py`, `core/render_assets.py`, `core/allocate.py`,
  `core/templates_table.py`, `core/catalog_models.py`, `assets/scenario/01_init_proxmox/`,
  `docs/box-template-image-field.md`.
