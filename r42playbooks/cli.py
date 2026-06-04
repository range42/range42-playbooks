"""Typer CLI — the msfvenom-style scenario generator frontend.

Commands:
  list <kind>   enumerate pickable catalog modules (boxes/subnets/policies/
                roles/containers) or existing generated scenarios
  show <module> describe one catalog module
  new <name>    compose a ScenarioSpec (from flags or --spec) and render a
                deployable scenarios/<name>/ tree

A thin shell over the frozen ``r42playbooks.api``: it parses args, prints, and
maps core errors to exit codes. No business logic lives here.
"""

from enum import Enum
from pathlib import Path
from typing import NoReturn

import typer
from pydantic import ValidationError as _PydValidationError

from r42playbooks import api
from r42playbooks.core.catalog import find_template_vm
from r42playbooks.core.errors import ScenarioExistsError, TopologyError
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.spec import ScenarioSpec

app = typer.Typer(help="range42 scenario generator (compose labs from the catalog)",
                  no_args_is_help=True)

_CatalogOpt = typer.Option(
    Path("../range42-catalog"), "--catalog",
    help="Path to the range42-catalog checkout",
)
_OutputOpt = typer.Option(Path("scenarios"), "-o", "--output", help="Scenarios output dir")
_ReservedOpt = typer.Option(None, "--reserved", help="Path to scenarios/_reserved.json")


class ListKind(str, Enum):
    boxes = "boxes"
    subnets = "subnets"
    policies = "policies"
    roles = "roles"
    containers = "containers"
    scenarios = "scenarios"


def _fail(message: str) -> NoReturn:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _load_catalog(catalog: Path | None) -> api.Catalog:
    if catalog is None:
        _fail("error: --catalog is required")
    try:
        return api.load_catalog(catalog)
    except TopologyError as exc:
        _fail(f"error: {exc}")


def _reserved(path: Path | None) -> ReservedIndex | None:
    if path is None:
        return None
    try:
        return ReservedIndex.from_file(path)
    except TopologyError as exc:
        _fail(f"error: {exc}")


# --- list ------------------------------------------------------------------

@app.command("list")
def list_cmd(
    kind: ListKind = typer.Argument(..., help="What to enumerate"),
    catalog: Path = _CatalogOpt,
    output: Path = _OutputOpt,
) -> None:
    """List pickable catalog modules, or existing generated scenarios."""
    if kind is ListKind.scenarios:
        for path in sorted(Path(output).glob("*/scenario.r42.yml")):
            typer.echo(path.parent.name)
        return

    cat = _load_catalog(catalog)
    if kind is ListKind.boxes:
        for name in sorted(cat.box_templates):
            bt = cat.box_templates[name]
            typer.echo(f"{name}\t{bt.role}\t{bt.template_vm}")
    elif kind is ListKind.subnets:
        for name in sorted(cat.subnet_layouts):
            typer.echo(name)
    elif kind is ListKind.policies:
        for name in sorted(cat.network_policies):
            typer.echo(name)
    elif kind is ListKind.roles:
        for name in sorted(cat.roles):
            typer.echo(name)
    elif kind is ListKind.containers:
        for name in sorted(cat.containers):
            typer.echo(name)


# --- show ------------------------------------------------------------------

@app.command()
def show(
    module: str = typer.Argument(..., help="A box / subnet / policy / role / container name"),
    catalog: Path = _CatalogOpt,
) -> None:
    """Describe a single catalog module (auto-detects its kind)."""
    cat = _load_catalog(catalog)

    if module in cat.box_templates:
        bt = cat.box_templates[module]
        typer.secho(f"box-template: {bt.id}", bold=True)
        if bt.description:
            typer.echo(f"  {bt.description}")
        typer.echo(f"  role:            {bt.role}")
        typer.echo(f"  inventory group: {bt.default_inventory_group}")
        resolved = find_template_vm(cat, bt.template_vm)
        if resolved:
            image_id, tpl = resolved
            typer.echo(f"  template_vm:     {bt.template_vm}  [{image_id}  vm_id={tpl.vm_id}  {tpl.spec}]")
        else:
            typer.echo(f"  template_vm:     {bt.template_vm}")
        attachments = bt.default_attachments or []
        typer.echo(f"  default roles:   {', '.join(a.catalog_ref for a in attachments) or '(none)'}")
    elif module in cat.subnet_layouts:
        sl = cat.subnet_layouts[module]
        typer.secho(f"subnet-layout: {sl.id}", bold=True)
        if sl.description:
            typer.echo(f"  {sl.description}")
        for s in sl.subnets:
            typer.echo(f"  - {s.name}={s.cidr}@{s.bridge}")
        if sl.template_subnet:
            ts = sl.template_subnet
            typer.echo(f"  template_subnet: {ts.cidr}@{ts.bridge}")
    elif module in cat.network_policies:
        pol = cat.network_policies[module]
        typer.secho(f"network-policy: {pol.id}", bold=True)
        typer.echo(f"  zones:    {', '.join(z.name for z in pol.zones)}")
        typer.echo(f"  services: {len(pol.services)}  matrix rules: {len(pol.matrix)}")
    elif module in cat.roles:
        typer.secho(f"role: {module}", bold=True)
    elif module in cat.containers:
        typer.secho(f"container: {module}", bold=True)
    else:
        _fail(f"error: no catalog module named {module!r}")


# --- new -------------------------------------------------------------------

def _print_manifest_summary(root: Path) -> None:
    """Print a compact VM/template table from the generated manifest."""
    import json
    manifest_path = root / "manifest" / "scenario_vms.json"
    if not manifest_path.is_file():
        return
    data = json.loads(manifest_path.read_text())
    templates = data.get("templates", [])
    vms = data.get("vms", [])
    if templates:
        typer.echo(f"\n  templates ({len(templates)}):")
        for t in templates:
            typer.echo(f"    {t['vm_id']}  {t['vm_name']}  [{t['image']}  {t['spec']}]")
    if vms:
        typer.echo(f"\n  boxes ({len(vms)}):")
        col = max(len(v["vm_name"]) for v in vms)
        for v in vms:
            typer.echo(f"    {v['vm_id']}  {v['vm_name']:<{col}}  {v['role']:<8}  {v['ip']}")


def _parse_box(raw: str) -> dict:
    """Parse a ``--box`` flag: ``template`` or ``template:count=5,template_vm_id=9244``."""
    template, _, rest = raw.partition(":")
    box: dict = {"template": template}
    if rest:
        for pair in rest.split(","):
            key, _, value = pair.partition("=")
            key = key.strip()
            if key not in ("count", "template_vm_id"):
                _fail(f"error: unknown box option {key!r} in --box {raw!r}")
            try:
                box[key] = int(value)
            except ValueError:
                _fail(f"error: --box {raw!r}: {key} must be an integer")
    return box


def _build_spec(
    name: str, subnet: str | None, policy: str | None, boxes: list[str],
    spec_file: Path | None, proxmox_node: str | None, notes: str | None,
) -> ScenarioSpec:
    """Build a ScenarioSpec from --spec (name-overridden) or from flags."""
    if spec_file is not None:
        try:
            loaded = api.load_spec(spec_file)
        except TopologyError as exc:
            _fail(f"error: {exc}")
        else:
            data = loaded.model_dump(mode="json")
            data["name"] = name  # positional name wins, so the output dir matches
    else:
        if not subnet:
            _fail("error: --subnet is required (or pass --spec)")
        if not boxes:
            _fail("error: at least one --box is required (or pass --spec)")
        data = {
            "name": name, "subnet_layout": subnet,
            "boxes": [_parse_box(b) for b in boxes],
        }
        if policy:  # optional + ignored by the generator (isolation = per-box firewall roles)
            data["network_policy"] = policy
        if proxmox_node:
            data["proxmox_node"] = proxmox_node
        if notes:
            data["notes"] = notes
    try:
        return ScenarioSpec.model_validate(data)
    except _PydValidationError as exc:
        _fail(f"error: invalid composition: {exc}")


@app.command()
def new(
    name: str = typer.Argument(..., help="Scenario name (no dots)"),
    subnet: str = typer.Option(None, "--subnet", help="subnet_layout template id"),
    policy: str = typer.Option(None, "--policy",
                               help="network_policy id (optional, currently unused by the generator)"),
    box: list[str] = typer.Option(None, "--box", help="template[:count=N,template_vm_id=ID]"),
    spec: Path = typer.Option(None, "--spec", help="Load a scenario.r42.yml instead of flags"),
    proxmox_node: str = typer.Option(None, "--proxmox-node", help="Target Proxmox node"),
    notes: str = typer.Option(None, "--notes", help="Free-text notes"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing scenario dir"),
    catalog: Path = _CatalogOpt,
    output: Path = _OutputOpt,
    reserved: Path = _ReservedOpt,
) -> None:
    """Compose a scenario and render a deployable scenarios/<name>/ tree."""
    cat = _load_catalog(catalog)
    composed = _build_spec(name, subnet, policy, box or [], spec, proxmox_node, notes)

    problems = api.validate_refs(composed, cat)
    if problems:
        for p in problems:
            typer.secho(f"  ✗ {p}", fg=typer.colors.RED)
        _fail(f"{len(problems)} unknown catalog reference(s)")

    try:
        root = api.render_scenario(
            composed, catalog=cat, dest=output, reserved=_reserved(reserved), overwrite=force
        )
    except ScenarioExistsError as exc:
        _fail(f"{exc}\n  pass --force to overwrite it")
    except TopologyError as exc:
        _fail(f"generate failed: {exc}")
    typer.secho(f"✓ generated {root}", fg=typer.colors.GREEN)
    _print_manifest_summary(root)


if __name__ == "__main__":
    app()
