"""Typer CLI — a thin frontend over r42playbooks.api / core.

Commands: author (scaffold a starter topology), validate, compile, show.
All real logic lives in the pure core; this module only parses args, prints,
and maps core errors to exit codes.
"""

from pathlib import Path
from typing import NoReturn

import typer

from r42playbooks import api
from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.compiler.network_policy import compile_network_policy
from r42playbooks.core.errors import TopologyError
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.io import dumps_topology, load_topology
from r42playbooks.core.scaffold import scaffold_topology

app = typer.Typer(help="range42 scenario authoring & topology compiler", no_args_is_help=True)

_CatalogOpt = typer.Option(..., "--catalog", help="Path to the range42-catalog checkout")
_ReservedOpt = typer.Option(None, "--reserved", help="Path to scenarios/_reserved.json")


def _reserved(path: Path | None) -> ReservedIndex:
    if path:
        return ReservedIndex.from_file(path)
    typer.secho(
        "⚠ no --reserved file: cross-scenario vm_id/IP collision checks are disabled",
        fg=typer.colors.YELLOW, err=True,
    )
    return ReservedIndex(entries=())


def _fail(message: str) -> NoReturn:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


@app.command()
def validate(
    topology: Path = typer.Argument(..., help="Path to topology.json"),
    catalog: Path = _CatalogOpt,
    reserved: Path = _ReservedOpt,
) -> None:
    """Validate a topology against schema, catalog, and the reservation registry."""
    try:
        cat = load_catalog(catalog)
        topo = load_topology(topology)
    except TopologyError as exc:
        _fail(f"error: {exc}")
    problems = api.validate_topology(topo, catalog=cat, reserved=_reserved(reserved))
    if problems:
        for p in problems:
            typer.secho(f"  ✗ {p}", fg=typer.colors.RED)
        _fail(f"{len(problems)} problem(s) found")
    typer.secho("✓ topology is valid", fg=typer.colors.GREEN)


@app.command("compile")
def compile_cmd(
    topology: Path = typer.Argument(..., help="Path to topology.json"),
    workspace: Path = typer.Option(..., "--workspace", help="Output workspace dir"),
    catalog: Path = _CatalogOpt,
    reserved: Path = _ReservedOpt,
) -> None:
    """Compile a topology into deploy artifacts under a workspace."""
    try:
        cat = load_catalog(catalog)
        topo = load_topology(topology)
        result = api.compile_topology(topo, workspace=workspace, catalog=cat,
                                      reserved=_reserved(reserved))
    except TopologyError as exc:
        _fail(f"compile failed: {exc}")
    typer.secho("✓ compiled", fg=typer.colors.GREEN)
    for label, path in (
        ("topology", result.topology_path),
        ("inventory", result.inventory_path),
        ("scenario_vms", result.scenario_vms_path),
        ("network_policy", result.network_policy_path),
        ("stages", result.stages_path),
    ):
        typer.echo(f"  {label:<14} {path}")


@app.command()
def author(
    scenario: str = typer.Option(..., "--scenario", help="Scenario name (no dots)"),
    layout: str = typer.Option(..., "--layout", help="subnet_layout template id"),
    policy: str = typer.Option(..., "--policy", help="network_policy template id"),
    catalog: Path = _CatalogOpt,
    output: Path = typer.Option(None, "-o", "--output", help="Write to file (default: stdout)"),
) -> None:
    """Scaffold a starter topology.json from a subnet layout + network policy."""
    try:
        cat = load_catalog(catalog)
        topo = scaffold_topology(cat, scenario=scenario, layout_id=layout, policy_id=policy)
    except TopologyError as exc:
        _fail(f"author failed: {exc}")
    text = dumps_topology(topo)
    if output:
        output.write_text(text, encoding="utf-8")
        typer.secho(f"✓ wrote {output}", fg=typer.colors.GREEN)
    else:
        typer.echo(text)


@app.command()
def show(
    topology: Path = typer.Argument(..., help="Path to topology.json"),
    catalog: Path = typer.Option(None, "--catalog", help="Catalog (required for --rules)"),
    rules: bool = typer.Option(False, "--rules", help="Also show compiled FORWARD rules"),
) -> None:
    """Print a topology summary; with --rules, also the compiled FORWARD table."""
    try:
        topo = load_topology(topology)
    except TopologyError as exc:
        _fail(f"error: {exc}")

    typer.secho(f"scenario: {topo.scenario}", bold=True)
    typer.echo(f"  subnets: {', '.join(f'{s.name}={s.cidr}@{s.bridge}' for s in topo.subnets)}")
    typer.echo(f"  zones:   {', '.join(f'{z.name}({z.role})' for z in topo.zones)}")
    typer.echo(f"  boxes:   {len(topo.boxes)}")
    for b in topo.boxes:
        typer.echo(f"    - {b.vm_name} id={b.vm_id} ip={b.ip} zone={b.zone} tmpl={b.box_template}")
    typer.echo(f"  policy:  {topo.network_policy.template}")

    if rules:
        if catalog is None:
            _fail("--rules requires --catalog")
        try:
            cat = load_catalog(catalog)
            pol = cat.resolve_network_policy(topo.network_policy.template)
            ver = cat.resolved_version("network_policies", pol.id)
            compiled = compile_network_policy(topo, pol, version=ver)
        except TopologyError as exc:
            _fail(f"error: {exc}")
        typer.secho(f"\nFORWARD rules ({pol.id}@{ver}):", bold=True)
        for r in compiled.rules:
            dst = r.destination or r.out_interface or "-"
            port = f":{r.destination_port}" if r.destination_port else ""
            typer.echo(f"  w{r.weight:<3} {r.jump:<6} {r.source or '-':<18} -> {dst}{port}")


if __name__ == "__main__":
    app()
