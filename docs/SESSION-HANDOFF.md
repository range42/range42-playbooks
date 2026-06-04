# Session handoff — r42playbooks generator

**Date:** 2026-06-04 (sessions 2+3). **Continue:** everything is **pushed**, don't rely on local state.

## Repos & branches
| repo | branch | resume with |
|---|---|---|
| `range42-playbooks` | `feat/r42playbooks-generator` | `git fetch && git checkout feat/r42playbooks-generator` |
| `range42-catalog` | `feat/topology-layer-templates` | `git fetch && git checkout feat/topology-layer-templates` |

Setup: `cd range42-playbooks && python3 -m venv .venv && .venv/bin/pip install -e ".[dev,cli,tui]"`
then `.venv/bin/python -m pytest -q` → **200 green**.

## CLI commands (current state)

```
r42playbooks list boxes|subnets|policies|roles|containers|images|scenarios
r42playbooks show <box|subnet|policy|image|role|container>
r42playbooks new <name> --subnet <id> --box <template>[:count=N] ... [--force] [--notes "..."]
r42playbooks validate <spec.r42.yml>
```

- `list boxes` and `list images` output aligned columns
- `show <box>` shows description + resolved template VM (image, vm_id, spec)
- `show <subnet>` shows description + template_subnet
- `show <image>` shows all proxmox_templates with vm_id+spec
- `new` prints manifest summary (templates + boxes) after generation
- `new` auto-detects `<output-dir>/_reserved.json` when not passed via `--reserved`
- `validate` runs `validate_refs` without writing any files (exit 0/1)
- `list scenarios` shows `<name>\t<subnet_layout>\t[box×count, ...]` one-liner
- `--notes` text is rendered as a blockquote in the generated `README.md`

## Architecture decisions LOCKED
- **`template_vm` reference**: box_template → `ProxmoxTemplateSpec.vm_name` (catalog-owned).
- **`ip_octet` in catalog**: only last octet, full IP = `{template_subnet.prefix}.{ip_octet}`.
- **Selective templates**: `alloc.templates` only contains template VMs the scenario needs.
- **Playbooks → catalog direction**: generator reads catalog by name only, never vendors code.

## Known architecture debt
- **`bundles/core/proxmox/configure/default/vms`**: dead code, superseded by the generator.
  Add deprecation READMEs **after confirmed by a real Proxmox deploy**.
- **box `cpu`/`ram` override**: spec fields exist but the renderer doesn't pass them to
  the clone play. Future enhancement: `qm set` after clone.

## Current state on the deployer (hv-lab-01)
- **Scenario `test_gen_lab`**: on the deployer, needs `git pull` to get latest generator.
- To sync: `cd range42-playbooks && git pull` then regenerate if needed.

## NEXT STEPS (priority order)
1. ⭐ **Validate on real Proxmox** — `range42-context use hv-lab-01 test_gen_lab` then
   `range42-context deploy`.  Key: template creation (9221 ubuntu + 9321 debian), VM cloning,
   `software.configure.firewalls` (ufw on Ubuntu minimal cloud image).
2. **Deprecate dead bundles** — `bundles/core/proxmox/configure/default/vms/` — after Proxmox deploy confirms.
3. **Merge devkit PR #112** (pending review).
4. **Reusable role profiles** (deferred): `05_topology_layer/role_profiles/` in catalog.

## Key files
`core/render.py`, `core/render_assets.py`, `core/allocate.py`, `core/catalog.py`,
`core/catalog_models.py`, `cli.py`, `tui/controller.py`

## Notes / gotchas
- Catalog is a separate gitignored sibling repo; tests use `fake_catalog` fixture.
- 200 tests green. Coverage 93%.
- `_reserved.json` is auto-detected from the output dir (both CLI and TUI controller).
- The linter (ruff) auto-reformats on commit — spacing diffs are normal.
- `scenarios/test_gen_lab` on the deployer is gitignored throwaway output — not committed.
