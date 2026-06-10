"""Typer CLI — the scenario generator frontend.

Commands:
  list <kind>      enumerate catalog modules (boxes/subnets/policies/roles/
                   containers/images) or existing generated scenarios
  show <module>    describe one catalog module (box, subnet, policy, image…)
  new <name>       compose a ScenarioSpec (from flags or --spec) and render a
                   deployable scenarios/<name>/ tree
  validate <spec>  typo-check a scenario.r42.yml against the catalog

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

app = typer.Typer(
    help="range42 scenario generator (compose labs from the catalog)",
    no_args_is_help=True,
)

_CatalogOpt = typer.Option(
    Path("../range42-catalog"),
    "--catalog",
    help="Path to the range42-catalog checkout",
)
_OutputOpt = typer.Option(
    Path("scenarios"), "-o", "--output", help="Scenarios output dir"
)
_ReservedOpt = typer.Option(
    None, "--reserved",
    help="Path to _reserved.json (auto-detected from output dir if present)",
)


class ListKind(str, Enum):
    boxes = "boxes"
    subnets = "subnets"
    policies = "policies"
    roles = "roles"
    containers = "containers"
    images = "images"
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
        paths = sorted(Path(output).glob("*/scenario.r42.yml"))
        if not paths:
            return
        for path in paths:
            try:
                spec = api.load_spec(path)
                boxes_summary = ", ".join(
                    f"{b.template}" + (f"×{b.count}" if b.count > 1 else "")
                    for b in spec.boxes
                )
                typer.echo(f"{spec.name}\t{spec.subnet_layout}\t[{boxes_summary}]")
            except Exception as exc:
                typer.secho(f"warning: could not parse {path}: {exc}", fg=typer.colors.YELLOW, err=True)
                typer.echo(path.parent.name)
        return

    cat = _load_catalog(catalog)
    if kind is ListKind.boxes:
        rows = [(name, cat.box_templates[name].template_vm)
                for name in sorted(cat.box_templates)]
        w0 = max(len(r[0]) for r in rows)
        for name, tvm in rows:
            typer.echo(f"{name:<{w0}}  {tvm}")
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
    elif kind is ListKind.images:
        rows_img = [(image_id, f"{cat.images[image_id].distro}/{cat.images[image_id].codename}",
                     f"{len(cat.images[image_id].proxmox_templates)} template(s)")
                    for image_id in sorted(cat.images)]
        w0 = max(len(r[0]) for r in rows_img)
        w1 = max(len(r[1]) for r in rows_img)
        for image_id, distro_codename, tpl_count in rows_img:
            typer.echo(f"{image_id:<{w0}}  {distro_codename:<{w1}}  {tpl_count}")


# --- show ------------------------------------------------------------------


@app.command()
def show(
    module: str = typer.Argument(
        ..., help="A box / subnet / policy / role / container name"
    ),
    catalog: Path = _CatalogOpt,
) -> None:
    """Describe a single catalog module (auto-detects its kind)."""
    cat = _load_catalog(catalog)

    if module in cat.box_templates:
        bt = cat.box_templates[module]
        typer.secho(f"box-template: {bt.id}", bold=True)
        if bt.description:
            typer.echo(f"  {bt.description}")
        resolved = find_template_vm(cat, bt.template_vm)
        if resolved:
            image_id, tpl = resolved
            typer.echo(
                f"  template_vm:     {bt.template_vm}  [{image_id}  vm_id={tpl.vm_id}  {tpl.spec}]"
            )
        else:
            typer.echo(f"  template_vm:     {bt.template_vm}")
        attachments = bt.default_attachments or []
        typer.echo(
            f"  default roles:   {', '.join(a.catalog_ref for a in attachments) or '(none)'}"
        )
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
    elif module in cat.images:
        img = cat.images[module]
        typer.secho(f"image: {img.id}", bold=True)
        if img.description:
            typer.echo(f"  {img.description}")
        typer.echo(f"  distro/codename: {img.distro}/{img.codename}")
        if img.cloud_image:
            typer.echo(f"  cloud_image:     {img.cloud_image.filename}")
        if img.proxmox_templates:
            typer.echo(f"  proxmox_templates ({len(img.proxmox_templates)}):")
            for tpl in img.proxmox_templates:
                typer.echo(f"    vm_id={tpl.vm_id}  {tpl.vm_name}  {tpl.spec}")
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
            typer.echo(
                f"    {v['vm_id']}  {v['vm_name']:<{col}}  {v['subnet']:<8}  {v['ip']}"
            )


def _parse_box(raw: str) -> dict:
    """Parse a ``--box`` flag: ``template`` or ``template:subnet=admin,count=5``."""
    template, _, rest = raw.partition(":")
    box: dict = {"template": template}
    if rest:
        for pair in rest.split(","):
            key, _, value = pair.partition("=")
            key = key.strip()
            if key == "subnet":
                box[key] = value.strip()
            elif key in ("count", "template_vm_id", "octet"):
                try:
                    box[key] = int(value)
                except ValueError:
                    _fail(f"error: --box {raw!r}: {key} must be an integer")
            else:
                _fail(f"error: unknown box option {key!r} in --box {raw!r}")
    return box


def _build_spec(
    name: str,
    subnet: str | None,
    policy: str | None,
    boxes: list[str],
    spec_file: Path | None,
    proxmox_node: str | None,
    notes: str | None,
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
            "name": name,
            "subnet_layout": subnet,
            "boxes": [_parse_box(b) for b in boxes],
        }
        if policy:
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
    policy: str = typer.Option(
        None,
        "--policy",
        help="network_policy id — emits 05_network_isolation/ iptables playbook",
    ),
    box: list[str] = typer.Option(
        None, "--box", help="template[:count=N,template_vm_id=ID]"
    ),
    spec: Path = typer.Option(
        None, "--spec", help="Load a scenario.r42.yml instead of flags"
    ),
    proxmox_node: str = typer.Option(
        None, "--proxmox-node", help="Target Proxmox node"
    ),
    notes: str = typer.Option(None, "--notes", help="Free-text notes"),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing scenario dir"
    ),
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

    # Auto-detect _reserved.json in the output dir when not explicitly passed.
    auto = output / "_reserved.json"
    effective_reserved = reserved if reserved is not None else (auto if auto.is_file() else None)

    try:
        root = api.render_scenario(
            composed,
            catalog=cat,
            dest=output,
            reserved=_reserved(effective_reserved),
            overwrite=force,
        )
    except ScenarioExistsError as exc:
        _fail(f"{exc}\n  pass --force to overwrite it")
    except TopologyError as exc:
        _fail(f"generate failed: {exc}")
    typer.secho(f"✓ generated {root}", fg=typer.colors.GREEN)
    _print_manifest_summary(root)


@app.command()
def validate(
    spec: Path = typer.Argument(..., help="Path to a scenario.r42.yml spec file"),
    catalog: Path = _CatalogOpt,
) -> None:
    """Validate a scenario.r42.yml spec against the catalog (no files written)."""
    cat = _load_catalog(catalog)
    try:
        composed = api.load_spec(spec)
    except TopologyError as exc:
        _fail(f"error: {exc}")

    problems = api.validate_refs(composed, cat)
    if problems:
        for p in problems:
            typer.secho(f"  ✗ {p}", fg=typer.colors.RED)
        _fail(f"{len(problems)} problem(s) found in {spec}")
    typer.secho(
        f"✓ {spec.name} — spec valid ({len(composed.boxes)} box(es), {composed.subnet_layout})",
        fg=typer.colors.GREEN,
    )


if __name__ == "__main__":
    app()
