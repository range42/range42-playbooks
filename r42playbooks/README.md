# r42playbooks

**msfvenom-style scenario generator for range42.**

`r42playbooks` lists the composable modules in `range42-catalog`, lets you compose a lab
(CLI flags, a `scenario.r42.yml` spec, or the TUI), and **generates a real
`scenarios/<name>/` directory** in the existing `demo_lab` format — deployable through the
normal range42 flow (`range42-context deploy`) with no changes elsewhere.

It is **not** the canonical topology engine for the gamenet "universal" playbook (that
convergence is parked on a separate branch, issue #67). A generated scenario references
catalog content **by name only** — Ansible roles resolve via `ANSIBLE_ROLES_PATH`, container
stacks via `RANGE42_INVENTORY__DOCKER__*` — so the generated tree stays a thin recipe of names,
never a copy of role code.

## Install

```bash
pip install r42playbooks            # pure core only (pydantic + pyyaml + stdlib)
pip install "r42playbooks[cli]"     # + Typer CLI
pip install "r42playbooks[tui]"     # + Textual TUI
```

## CLI (`list` / `show` / `new`)

```bash
# explore the catalog
r42playbooks list boxes      --catalog ../range42-catalog
r42playbooks list subnets    --catalog ../range42-catalog
r42playbooks list policies   --catalog ../range42-catalog
r42playbooks list roles      --catalog ../range42-catalog
r42playbooks list containers --catalog ../range42-catalog
r42playbooks show vuln-box   --catalog ../range42-catalog

# compose + generate a scenario from flags
r42playbooks new my_lab \
    --subnet default-3zone --policy air-gap-ctf \
    --box admin-wazuh --box vuln-box:count=5 \
    --catalog ../range42-catalog -o scenarios/

# or regenerate from a saved composition (written into every scenario)
r42playbooks new my_lab --spec scenarios/my_lab/scenario.r42.yml \
    --catalog ../range42-catalog -o scenarios/
```

## TUI

```bash
r42playbooks-tui ../range42-catalog
```

Pick a name, subnet layout, and network policy; add boxes (with a count); preview the
allocation; generate.

## Library (`import r42playbooks`)

The stable surface is re-exported at the package root so a downstream tool
(`r42deploy`/`r42runtime`, the range42 deployment CLI/TUI) can drive generation by import alone:

```python
import r42playbooks as r

catalog = r.load_catalog("/path/to/range42-catalog")
spec = r.load_spec("scenario.r42.yml")          # or r.ScenarioSpec.model_validate({...})

problems = r.validate_refs(spec, catalog)        # typo guard — [] means every ref resolves
if not problems:
    root = r.render_scenario(spec, catalog=catalog, dest="scenarios/")
    print(f"generated {root}")
```

Everything raises the `r42playbooks.core.errors` hierarchy (`TopologyError` and subclasses) —
never a framework type. Frozen entry points: `load_catalog`, `list_roles`, `list_containers`,
`validate_refs`, `load_spec`, `allocate`, `render_scenario(spec, *, catalog, dest, reserved=None)`.

## What gets generated

```
scenarios/<name>/
  scenario.r42.yml              # the composition (re-runnable)
  main.yml / main_vms_only.yml  # import skeleton (only the emitted sections)
  01_init_proxmox/templates/    # 9xxx Proxmox template creation (vendored, verbatim)
  NN_<section>/                 # 02_admin / 03_student / 04_ctf, per composed box role
    _main.yml                   # stage imports + per-VM global_* overrides
    stage_00/<vm>.yml           # clone Proxmox template -> create VM
    stage_01/<vm>.yml           # roles: [<catalog role NAMES>]  + <vm>.devkit/
  manifest/scenario_vms.json    # allocated vm_id / ip (octet rule, _reserved.json aware)
  templates/                    # ansible-inventory.j2, ssh-config.j2, ansible-vars.yml, vault-example.yml
  <name>.setup.sh / .delete_all.sh / reset scripts
```

`secrets/` is **not** generated — it is a deploy-time symlink created by `range42-context use`.

## Develop

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

See [`docs/r42playbooks-plan.md`](../docs/r42playbooks-plan.md) for the full build plan and status.

GPL-3.0.
