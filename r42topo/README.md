# r42topo

The range42 **canonical topology engine**.

`r42topo` speaks the canonical *Range42 Scenario Schema v1* (`CatalogEntry` / `ProjectOverlay`
with a unified `nodes[]` array, generated into `core/canonical.py`). It turns a declarative,
schema-validated document into the artifacts a deploy needs — composing overlays, expanding
per-team replication, deriving VMID/IP allocation, running preflight checks, and emitting the
static Ansible inventory (`hosts.yml`).

It is the shared engine of the convergence in [issue #67](../docs/r42topo-convergence-plan.md):
one engine, conforming to the schema owned by `range42-deployer-ui`, validated by the shared
test-vectors. The earlier invented `subnets/zones/boxes` model + iptables compiler has been
**retired** in favour of the canonical contract.

## Consumers

The **pure core** (`r42topo.core`, `r42topo.api`) is framework-agnostic and imported by:

- **range42-backend-api** (FastAPI) — the *managed* deploy path (UI → backend → runner).
- **r42deploy** (CLI/TUI) — the *infra-as-code* path: compose → expand → inventory → deploy
  with **no backend and no UI required** (`r42topo` + `r42runtime`).
- **r42topo's own Typer CLI** (`r42topo …`) — a thin frontend for the IaC path.

`core/` imports only pydantic, pyyaml, and the stdlib — no FastAPI, httpx, asyncio, or DB.
The CLI is an optional extra (`pip install r42topo[cli]`).

## CLI

```bash
r42topo scaffold --name "My Lab" -o topology.json   # start from a valid skeleton
r42topo validate topology.json                      # schema check
r42topo compose base.json --overlay overlay.json    # effective doc + hash
r42topo expand topology.json --teams 4              # per-team expansion
r42topo preflight topology.json --teams 4           # pure sync checks
r42topo inventory topology.json --teams 4 \
    --codename LAB --proxmox 10.0.0.1 --ssh-keys ./keys -o hosts.yml
```

## Schema

The canonical schema is **vendored** under [`schema/`](schema/) (source of truth:
`range42-deployer-ui`). `core/canonical.py` is generated from it via `datamodel-codegen` — see
[`schema/SOURCE.md`](schema/SOURCE.md). Deploying a scenario needs **zero deployer-ui link at
runtime**; the schema is a build-time concern only.

## Develop

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,cli]"
PYTHONPATH=. pytest --cov=r42topo
```

GPL-3.0.
