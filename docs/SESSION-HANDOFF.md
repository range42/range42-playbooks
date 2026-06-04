# Session handoff — r42playbooks generator

**Date:** 2026-06-04. **Continue:** next session on a **different PC** → everything
below is **pushed** (both repos), don't rely on local-only state or `.claude` memory.

## Repos & branches
| repo | branch | resume with |
|---|---|---|
| `range42-playbooks` | `feat/r42playbooks-generator` | `git fetch && git checkout feat/r42playbooks-generator` |
| `range42-catalog` | `feat/topology-layer-templates` | `git fetch && git checkout feat/topology-layer-templates` |

Setup: `cd range42-playbooks && python3 -m venv .venv && .venv/bin/pip install -e ".[dev,cli,tui]"`
then `.venv/bin/python -m pytest -q` → **190 green**.

Generator entry point:
```
.venv/bin/python -m r42playbooks.cli new my_lab \
  --subnet default-3zone --box vuln-box:count=2 --box debian-jump \
  --catalog ../range42-catalog -o scenarios/
```

## What changed THIS session (major refactors)

### 1. `01_image_layer` created in the catalog
The catalog now owns ALL ingredients — `01_image_layer/<image>/image.yml` carries:
- `cloud_image: {url, filename}` — download coordinates for stage_00
- `proxmox_templates: [{vm_id, vm_name, spec, ip_octet}]` — Proxmox template VM specs
  for stage_01; vm_names follow `template-vm-{distro}-{codename}-*` convention
- `ip_octet` only (last octet) — full IP derived at allocation from `template_subnet`

### 2. `BoxTemplate` refactored: `spec` + `image` → `template_vm`
`BoxTemplate.template_vm` is a direct reference to a `ProxmoxTemplateSpec` by `vm_name`
(globally unique across all images). The generator resolves `template_vm` → image + spec
via `find_template_vm(catalog, vm_name)`. No more fuzzy `select_template` / `TEMPLATE_TABLE`.

### 3. Selective template rendering
`alloc.templates` is now the **deduplicated set of template VMs the scenario actually
needs** (not the full image table). A scenario with only `debian-jump` creates only
`template-vm-debian-trixie-small` (9321) — no ubuntu_noble files at all.

### 4. `template_subnet` in SubnetLayout
`SubnetLayout.template_subnet: TemplateSubnet | None` carries the Proxmox infrastructure
subnet (bridge + cidr) used for template VM creation. Separate from lab zones (the
"3" in `default-3zone` remains accurate). The renderer derives template VM IPs as
`{template_subnet.cidr_prefix}.{tpl.ip_octet}`.

### 5. `assets/` directory eliminated
ALL `01_init_proxmox` content is now rendered from catalog data or `render_assets.py`
constants. No static asset files remain. `templates_table.py` deleted.

### 6. Devkit bug fixed (PR #112, branch `fix/devkit-codename-host-pattern-non-tty-stdin`)
Two bugs in `range42-ansible_roles-debug-devkit` broke `range42-context delete-everything`:
- `proxmox_node` (PVE node name) was used as Ansible `- hosts:` pattern; should be the
  codename (`RANGE42_INFRASTRUCTURE_CODENAME`). Fix in `proxmox__inc.jsons.basic_vm_actions`.
- `[ -t 0 ]` inside `$()` means non-TTY → `cat -` returns empty → no JSON output.
  Fix in `devkit_proxmox.STDIN.stdin_or_jsons`.
Fix is applied on the deployer and pushed. PR #112 open targeting `dev`, closes issue #111.

## Architecture decisions LOCKED
(See previous handoffs for the full list — all still apply.)

- **`template_vm` reference**: box_template → `ProxmoxTemplateSpec.vm_name` (catalog-owned).
  No more spec-based lookup or fuzzy fallback. Adding a new VM size = add to catalog only.
- **`ip_octet` in catalog**: only the last octet (deployment-independent). Full IP =
  `{template_subnet.prefix}.{ip_octet}`. Bridge from `template_subnet.bridge`.
- **Selective templates**: `alloc.templates` is scenario-specific. The manifest and
  stage_01 only contain the template VMs actually used.
- **Playbooks → catalog direction** holds with no exception.

## Known architecture debt
- **`--force` flag on `cli new` doesn't clean first**: generated scenario gets old files
  mixed with new ones (old numbered `00-template-vm-*.yml` stay alongside new
  `template-vm-ubuntu-noble-*.yml`). The `_main_*.yml` only imports new names so it's
  harmless, but worth fixing: add `shutil.rmtree(root)` before writing when `overwrite=True`.
- **`bundles/core/proxmox/configure/default/vms`**: dead code, superseded by the generator.
  Add deprecation READMEs when confirmed by a real Proxmox deploy.

## Current state on the deployer (hv-lab-01)
- **Proxmox**: clean — 0 VMs, 0 templates, clean iptables
- **Scenario `test_gen_lab`**: regenerated with latest code, correct manifest:
  - templates: 2 only (9221 `template-vm-ubuntu-noble-small-01-4g-32g`,
    9321 `template-vm-debian-trixie-small`)
  - vms: 3 (debian-jump, vuln-box-00, vuln-box-01)
- **Workspace**: `hv-lab-01-test_gen_lab` configured — activate with:
  `range42-context use hv-lab-01 test_gen_lab`
- **Repos**: both at latest commit

## NEXT STEPS (priority order)
1. ⭐ **Validate on real Proxmox** — run `range42-context deploy` on the deployer.
   Full flow: template creation (9221 ubuntu + 9321 debian), VM cloning, roles.
   Key validation: `software.configure.firewalls` (ufw install on Ubuntu minimal cloud image).
2. **Fix `--force` overwrite**: `render_scenario(overwrite=True)` should clean first
   (`shutil.rmtree(root)` before writing).
3. **Deprecate dead bundles**: `bundles/core/proxmox/configure/default/vms/create-vms-*`.
4. **Merge devkit PR #112** once reviewed.
5. **Reusable role profiles** (deferred): `05_topology_layer/role_profiles/` in catalog.

## Key files
`core/render.py`, `core/render_assets.py`, `core/allocate.py`, `core/catalog.py`,
`core/catalog_models.py`

## Notes / gotchas
- Catalog is a separate gitignored sibling repo; tests use `fake_catalog` fixture.
- 190 tests green (was 195; delta = 5 deleted `select_template` tests from removed
  `templates_table.py`).
- `scenarios/test_gen_lab` on the deployer is gitignored throwaway output — not committed.
