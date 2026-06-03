# r42playbooks

Scenario authoring & topology compiler for range42.

`r42playbooks` turns a declarative, pydantic-validated **`topology.json`** into the Ansible
artifacts a deploy needs (inventory, `scenario_vms.json`, network-isolation policy, stage
wiring), then resolves the extravars the `_universal` scenario consumes.

## Consumers

The **pure core** (`r42playbooks.core`, `r42playbooks.api`) is framework-agnostic and imported by:

- **range42-backend-api** (FastAPI) — authors/compiles topologies, then runs `_universal`.
- **r42playbooks's own CLI/TUI** — Typer CLI (`r42playbooks …`) and Textual TUI.
- **the range42 deployment CLI/TUI** (rewrite in progress) — same core, no duplication.

`core/` imports only pydantic, pyyaml, and the stdlib. CLI/TUI deps are optional extras
(`pip install r42playbooks[cli]`, `[tui]`) so the backend installs the core alone.

## Status

Early development. See [`docs/r42playbooks-plan.md`](../docs/r42playbooks-plan.md) for the full plan
and build order. Phase 1 (core models + IO) is implemented and tested.

## Develop

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
PYTHONPATH=. pytest --cov=r42playbooks.core
```

GPL-3.0.
