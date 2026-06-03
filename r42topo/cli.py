"""Typer CLI — a thin frontend over r42topo.api / core, on the canonical doc.

Commands operate on canonical ``CatalogEntry`` / ``ProjectOverlay`` documents
(``nodes[]``): validate, compose, expand, inventory, preflight, scaffold, show.
All real logic lives in the pure core; this module only parses args, prints,
and maps core errors to exit codes — so the infra-as-code path needs neither
the backend nor the UI.
"""
from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer

from r42topo import api
from r42topo.core.errors import TopologyError

app = typer.Typer(
    help="range42 canonical topology engine (compose / expand / inventory)",
    no_args_is_help=True,
)

_TeamsOpt = typer.Option(1, "--teams", min=1, help="Team count for per-team expansion")
_OutOpt = typer.Option(None, "-o", "--output", help="Write to file (default: stdout)")


def _fail(message: str) -> NoReturn:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _load(path: Path) -> dict:
    try:
        return api.load_document(path)
    except TopologyError as exc:
        _fail(f"error: {exc}")


def _emit(doc: dict, output: Path | None) -> None:
    text = api.dumps_canonical(doc)
    if output:
        api.dump_text_atomic(text, output)  # atomic: no torn artifact feeds the next step
        typer.secho(f"✓ wrote {output}", fg=typer.colors.GREEN, err=True)
    else:
        typer.echo(text, nl=False)


@app.command()
def validate(topology: Path = typer.Argument(..., help="Path to a canonical document")) -> None:
    """Validate a document against the canonical schema."""
    doc = _load(topology)
    try:
        api.validate_document(doc)
    except TopologyError as exc:
        _fail(f"✗ {exc}")
    typer.secho("✓ document is a valid CatalogEntry", fg=typer.colors.GREEN)


@app.command("compose")
def compose_cmd(
    base: Path = typer.Argument(..., help="Path to the base CatalogEntry"),
    overlay: Path = typer.Option(None, "--overlay", help="Path to a ProjectOverlay"),
    output: Path = _OutOpt,
) -> None:
    """Compose base + overlay into the effective document (prints its hash)."""
    base_doc = _load(base)
    overlay_doc = _load(overlay) if overlay else None
    eff, doc_hash = api.compose_effective(base_doc, overlay_doc)
    typer.secho(f"effective_doc_hash: {doc_hash}", fg=typer.colors.CYAN, err=True)
    _emit(eff, output)


@app.command()
def expand(
    topology: Path = typer.Argument(..., help="Path to a canonical document"),
    teams: int = _TeamsOpt,
    output: Path = _OutOpt,
) -> None:
    """Expand per-team nodes into N teams; emit the expanded document."""
    doc = _load(topology)
    result = api.expand_replication(doc, teams)
    _emit(result["document"], output)


@app.command()
def inventory(
    topology: Path = typer.Argument(..., help="Path to a canonical document"),
    teams: int = _TeamsOpt,
    codename: str = typer.Option(..., "--codename", help="Workspace codename"),
    proxmox: str = typer.Option(..., "--proxmox", help="Proxmox API address"),
    ssh_keys: Path = typer.Option(..., "--ssh-keys", help="Dir with admin_keys/ + student_keys/"),
    output: Path = typer.Option(..., "-o", "--output", help="Output hosts.yml path"),
) -> None:
    """Render the static Ansible inventory (hosts.yml) for a topology."""
    doc = _load(topology)
    try:
        api.validate_document(doc)  # schema + deny-list before producing a deploy artifact
        api.write_inventory(
            topology=doc, team_count=teams, codename=codename,
            proxmox_address=proxmox, ssh_keys_dir=ssh_keys, dest=output,
        )
    except (TopologyError, ValueError) as exc:
        _fail(f"inventory failed: {exc}")
    typer.secho(f"✓ wrote {output}", fg=typer.colors.GREEN)


@app.command()
def preflight(
    topology: Path = typer.Argument(..., help="Path to a canonical document"),
    teams: int = _TeamsOpt,
) -> None:
    """Run the pure synchronous preflight checks; exit non-zero on a block."""
    doc = _load(topology)
    report = api.preflight_document(doc, team_count=teams)
    color = {"pass": typer.colors.GREEN, "warn": typer.colors.YELLOW, "block": typer.colors.RED}
    for c in report.checks:
        typer.secho(f"  [{c.result}] {c.check}: {c.detail}", fg=color.get(c.result))
    typer.secho(f"result: {report.result}", bold=True, fg=color.get(report.result))
    if report.result == "block":
        raise typer.Exit(code=1)


@app.command()
def scaffold(
    name: str = typer.Option(..., "--name", help="Human-readable scenario name"),
    naming_prefix: str = typer.Option("lab", "--naming-prefix", help="Hostname prefix"),
    output: Path = _OutOpt,
) -> None:
    """Emit a minimal, valid canonical gamenet document to start from.

    Includes one shared admin VM and one per-team node so ``expand`` and
    ``preflight`` are immediately demonstrable. ``template_vmid`` is the Proxmox
    template VMID to clone from — replace the placeholders with your real
    template IDs (kept below 9000 here so the scaffold passes preflight; the
    9000-9999 band is protected).
    """
    doc = {
        "schema_version": "1.0",
        "kind": "gamenet",
        "name": name,
        "naming_prefix": naming_prefix,
        "bridge_base": 140,
        "nodes": [
            {
                "id": "admin-01",
                "kind": "vm",
                "role": "admin",
                "replication": {"scope": "shared"},
                "template_vmid": 8001,
                "config": {"cores": 2, "memory": 2048},
                "attachments": [],
            },
            {
                "id": "trainee",
                "kind": "vm",
                "role": "team",
                "replication": {"scope": "per_team"},
                "template_vmid": 8002,
                "config": {"cores": 2, "memory": 2048},
                "attachments": [],
            },
        ],
    }
    try:
        api.validate_document(doc)
    except TopologyError as exc:  # pragma: no cover - defensive
        _fail(f"scaffold produced an invalid document: {exc}")
    _emit(doc, output)
    if output:
        typer.secho(
            "  → edit template_vmid to your Proxmox template IDs before deploying",
            fg=typer.colors.CYAN, err=True,
        )


@app.command()
def show(topology: Path = typer.Argument(..., help="Path to a canonical document")) -> None:
    """Print a one-line-per-node summary of a topology."""
    doc = _load(topology)
    typer.secho(f"name: {doc.get('name', '?')}  kind: {doc.get('kind', '?')}", bold=True)
    typer.echo(f"  naming_prefix: {doc.get('naming_prefix', '-')}  bridge_base: {doc.get('bridge_base', '-')}")
    nodes = doc.get("nodes") or []
    typer.echo(f"  nodes: {len(nodes)}")
    for n in nodes:
        scope = (n.get("replication") or {}).get("scope", "-")
        typer.echo(
            f"    - {n.get('id'):<16} kind={n.get('kind'):<8} "
            f"role={n.get('role') or '-':<8} scope={scope}"
        )


if __name__ == "__main__":
    app()
