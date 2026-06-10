"""Catalog loader: resolve + validate 05_topology_layer templates from disk.

Layout (directory-per-version):
    <catalog_root>/05_topology_layer/<category>/<id>/v<MAJOR>.<MINOR>.<PATCH>/template.yml

For each (category, id) the highest version is selected, parsed, validated
against its pydantic model, and content-hashed (sha256 of the raw file) so a
compile can record exactly which template version produced an artifact.

Security posture mirrors the backend's checks_playbooks.py: template ids are
regex-validated, resolved with strict=True, asserted to stay inside the layer
root, and symlinks escaping the root are rejected.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import ValidationError as _PydValidationError

from r42playbooks.core import constants as C
from r42playbooks.core.catalog_models import (
    BoxTemplate,
    ImageDef,
    NetworkPolicyTemplate,
    ProxmoxTemplateSpec,
    SubnetLayout,
)
from r42playbooks.core.errors import CatalogNotFoundError, ValidationError

if TYPE_CHECKING:
    from r42playbooks.core.spec import ScenarioSpec

_CATEGORY_MODEL = {
    C.CATEGORY_BOX_TEMPLATES: BoxTemplate,
    C.CATEGORY_NETWORK_POLICIES: NetworkPolicyTemplate,
    C.CATEGORY_SUBNET_LAYOUTS: SubnetLayout,
}


@dataclass(frozen=True)
class _Resolved:
    """A loaded template plus the version + content hash it came from."""

    model: object
    version: str
    sha256: str


@dataclass
class Catalog:
    """In-memory index of validated catalog templates + pickable refs."""

    # 01_image_layer — base VM image descriptors (optional; empty when layer absent)
    images: dict[str, ImageDef] = field(default_factory=dict)
    # 05_topology_layer categories
    box_templates: dict[str, BoxTemplate] = field(default_factory=dict)
    network_policies: dict[str, NetworkPolicyTemplate] = field(default_factory=dict)
    subnet_layouts: dict[str, SubnetLayout] = field(default_factory=dict)
    # name-referenced modules from 02_/03_ (not pydantic templates) — see S3.
    roles: set[str] = field(default_factory=set)
    containers: set[str] = field(default_factory=set)
    _resolved: dict[tuple[str, str], _Resolved] = field(
        default_factory=dict, init=False, repr=False
    )

    # -- resolution helpers (raise CatalogNotFoundError on miss) --

    def resolve_box_template(self, ref: str) -> BoxTemplate:
        return self._resolve(C.CATEGORY_BOX_TEMPLATES, ref, self.box_templates)

    def resolve_network_policy(self, ref: str) -> NetworkPolicyTemplate:
        return self._resolve(C.CATEGORY_NETWORK_POLICIES, ref, self.network_policies)

    def resolve_subnet_layout(self, ref: str) -> SubnetLayout:
        return self._resolve(C.CATEGORY_SUBNET_LAYOUTS, ref, self.subnet_layouts)

    def resolved_version(self, category: str, template_id: str) -> str:
        return self._resolved_entry(category, template_id).version

    def resolved_hash(self, category: str, template_id: str) -> str:
        return self._resolved_entry(category, template_id).sha256

    def _resolved_entry(self, category: str, template_id: str) -> _Resolved:
        try:
            return self._resolved[(category, template_id)]
        except KeyError:
            raise CatalogNotFoundError(
                f"{category} template not in resolved index: {template_id!r}"
            ) from None

    def _resolve(self, category: str, ref: str, index: dict):
        # ref is a bare template id (version pinning via @range is a later refinement)
        if not C.TEMPLATE_ID_RE.fullmatch(ref):
            raise CatalogNotFoundError(f"invalid template id: {ref!r}")
        try:
            return index[ref]
        except KeyError:
            raise CatalogNotFoundError(
                f"{category} template not found: {ref!r}"
            ) from None


def _highest_version_dir(template_dir: Path) -> tuple[Path, tuple[int, int, int]]:
    """Return (version_dir, parsed_semver) for the highest vX.Y.Z under a template."""
    best: tuple[tuple[int, int, int], Path] | None = None
    for child in template_dir.iterdir():
        if not child.is_dir():
            continue
        m = C.VERSION_DIR_RE.fullmatch(child.name)
        if not m:
            continue
        sem = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if best is None or sem > best[0]:
            best = (sem, child)
    if best is None:
        raise CatalogNotFoundError(f"no versioned template under {template_dir}")
    return best[1], best[0]


def _load_category(layer_root: Path, category: str, catalog: Catalog) -> None:
    """Load every template id under a category into the catalog index."""
    category_dir = (layer_root / category).resolve()
    if not category_dir.is_dir():
        return  # category optional
    if not category_dir.is_relative_to(layer_root):  # symlink escape guard
        raise CatalogNotFoundError(f"category escapes layer root: {category}")

    model_cls = _CATEGORY_MODEL[category]
    index = {
        C.CATEGORY_BOX_TEMPLATES: catalog.box_templates,
        C.CATEGORY_NETWORK_POLICIES: catalog.network_policies,
        C.CATEGORY_SUBNET_LAYOUTS: catalog.subnet_layouts,
    }[category]

    for template_dir in sorted(category_dir.iterdir()):
        if not template_dir.is_dir():
            continue
        template_id = template_dir.name
        if not C.TEMPLATE_ID_RE.fullmatch(template_id):
            raise ValidationError(f"invalid template id directory: {template_id!r}")

        version_dir, sem = _highest_version_dir(template_dir)
        template_file = (version_dir / "template.yml").resolve(strict=True)
        if not template_file.is_relative_to(layer_root):
            raise CatalogNotFoundError(f"template escapes layer root: {template_file}")

        raw = template_file.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        data = yaml.safe_load(raw.decode("utf-8"))
        try:
            model = model_cls.model_validate(data)
        except _PydValidationError as exc:  # pydantic ValidationError -> our ValidationError
            raise ValidationError(
                f"invalid {category} template {template_id!r}: {exc}"
            ) from exc

        if model.id != template_id:
            raise ValidationError(
                f"template id {model.id!r} does not match directory {template_id!r}"
            )

        index[template_id] = model
        catalog._resolved[(category, template_id)] = _Resolved(
            model=model, version=f"{sem[0]}.{sem[1]}.{sem[2]}", sha256=sha
        )


def _load_image_layer(catalog_root: Path, catalog: Catalog) -> None:
    """Load every image descriptor from ``01_image_layer/`` into *catalog*.

    The layer is optional — absent dirs are silently skipped so old/minimal
    catalogs remain loadable. Each ``<name>/v*/image.yml`` file is validated
    against :class:`~r42playbooks.core.catalog_models.ImageDef`.
    """
    layer_root = (Path(catalog_root) / C.IMAGE_LAYER_DIR).resolve()
    if not layer_root.is_dir():
        return

    for image_dir in sorted(layer_root.iterdir()):
        if not image_dir.is_dir():
            continue
        image_id = image_dir.name
        if not C.IMAGE_RE.fullmatch(image_id):
            raise ValidationError(f"invalid image id directory: {image_id!r}")

        version_dir, _ = _highest_version_dir(image_dir)
        image_file = (version_dir / "image.yml").resolve(strict=True)
        if not image_file.is_relative_to(layer_root):
            raise CatalogNotFoundError(f"image escapes layer root: {image_file}")

        raw = image_file.read_bytes()
        data = yaml.safe_load(raw.decode("utf-8"))
        try:
            model = ImageDef.model_validate(data)
        except _PydValidationError as exc:
            raise ValidationError(f"invalid image {image_id!r}: {exc}") from exc

        if model.id != image_id:
            raise ValidationError(
                f"image id {model.id!r} does not match directory {image_id!r}"
            )

        catalog.images[image_id] = model

    # Enforce global uniqueness of template vm_names across all images.
    seen: dict[str, str] = {}  # vm_name -> image_id
    for image_id, img_def in catalog.images.items():
        for tpl in img_def.proxmox_templates:
            if tpl.vm_name in seen:
                raise ValidationError(
                    f"template vm_name {tpl.vm_name!r} appears in both "
                    f"{seen[tpl.vm_name]!r} and {image_id!r} — vm_names must be "
                    f"globally unique so box_template.template_vm can resolve unambiguously"
                )
            seen[tpl.vm_name] = image_id


def find_template_vm(
    catalog: "Catalog", vm_name: str
) -> "tuple[str, ProxmoxTemplateSpec] | None":
    """Return ``(image_id, ProxmoxTemplateSpec)`` for *vm_name*, or ``None``.

    vm_names are globally unique across all images (enforced by ``_load_image_layer``),
    so the first match is the only match.
    """
    for image_id, img_def in catalog.images.items():
        for tpl in img_def.proxmox_templates:
            if tpl.vm_name == vm_name:
                return image_id, tpl
    return None


def list_images(catalog_root: Path) -> list[str]:
    """Enumerate base image ids from ``01_image_layer/``.

    Returns a sorted list of image id strings (e.g. ``["debian_trixie",
    "ubuntu_noble"]``).  Returns an empty list when the layer is absent.
    """
    layer_root = (Path(catalog_root) / C.IMAGE_LAYER_DIR).resolve()
    if not layer_root.is_dir():
        return []
    ids: list[str] = []
    for image_dir in sorted(layer_root.iterdir()):
        if not image_dir.is_dir():
            continue
        if C.IMAGE_RE.fullmatch(image_dir.name):
            ids.append(image_dir.name)
    return ids


def list_roles(catalog_root: Path) -> list[str]:
    """Enumerate reusable Ansible role names under ``02_ansible_layer/**/roles/``.

    Roles are referenced by name (``<category>.<action>.<target>``) and resolve at
    deploy time via ``ANSIBLE_ROLES_PATH`` — this is a read-only name scan, never a
    copy. Returns a sorted, de-duplicated list. Empty if the layer is absent.
    """
    layer_root = (Path(catalog_root) / C.ANSIBLE_LAYER_DIR).resolve()
    if not layer_root.is_dir():
        return []
    names: set[str] = set()
    for roles_dir in layer_root.rglob(C.ROLES_DIR_NAME):
        if not roles_dir.is_dir() or not roles_dir.resolve().is_relative_to(layer_root):
            continue  # skip symlink escapes
        for child in roles_dir.iterdir():
            if child.is_dir() and C.CATALOG_REF_RE.fullmatch(child.name):
                names.add(child.name)
    return sorted(names)


def list_containers(catalog_root: Path) -> list[str]:
    """Enumerate CTF docker stacks under ``03_container_layer/docker/_ctf/``.

    A container ref is the POSIX path, relative to ``_ctf/``, of a directory that
    holds a compose file (e.g. ``cve/web/dvwa``). Returns a sorted list. Empty if
    the layer is absent.
    """
    ctf_root = (Path(catalog_root) / C.CONTAINER_LAYER_DIR / C.CTF_REL_DIR).resolve()
    if not ctf_root.is_dir():
        return []
    refs: set[str] = set()
    for filename in C.COMPOSE_FILENAMES:
        for compose in ctf_root.rglob(filename):
            stack_dir = compose.parent.resolve()
            if not stack_dir.is_relative_to(ctf_root):
                continue  # skip symlink escapes
            rel = stack_dir.relative_to(ctf_root).as_posix()
            if rel and rel != ".":
                refs.add(rel)
    return sorted(refs)


def load_catalog(catalog_root: Path) -> Catalog:
    """Load + validate all catalog layers from a catalog checkout.

    Loads (in order): 01_image_layer (optional), 05_topology_layer (required),
    02_ansible_layer roles, 03_container_layer containers.

    :param catalog_root: path that contains ``05_topology_layer/``.
    :raises CatalogNotFoundError: if ``05_topology_layer`` is absent.
    :raises ValidationError: if any template file fails schema validation.
    """
    layer_root = (Path(catalog_root) / C.TOPOLOGY_LAYER_DIR).resolve()
    if not layer_root.is_dir():
        raise CatalogNotFoundError(f"missing {C.TOPOLOGY_LAYER_DIR} under {catalog_root}")

    catalog = Catalog()
    _load_image_layer(catalog_root, catalog)
    for category in _CATEGORY_MODEL:
        _load_category(layer_root, category, catalog)
    catalog.roles = set(list_roles(catalog_root))
    catalog.containers = set(list_containers(catalog_root))
    return catalog


def validate_refs(spec: "ScenarioSpec", catalog: Catalog) -> list[str]:
    """Return human-readable messages for every spec ref missing from *catalog*.

    A typo guard for ``scenario.r42.yml``: checks the subnet layout, network
    policy, each box template, its base image (when 01_image_layer is loaded),
    and every attachment that becomes a generated role name — both the box's
    catalog ``default_attachments`` and the spec's ``attachments_add`` (the
    renderer emits both, so both must resolve). An empty list means every
    referenced module exists. ``gamification`` attachments are not enumerated
    here and are skipped (cannot be validated by name yet).
    """
    problems: list[str] = []
    if spec.subnet_layout not in catalog.subnet_layouts:
        problems.append(f"unknown subnet_layout: {spec.subnet_layout!r}")
    # network_policy is optional + ignored by the generator; typo-guard only if set.
    if spec.network_policy is not None and spec.network_policy not in catalog.network_policies:
        problems.append(f"unknown network_policy: {spec.network_policy!r}")
    for box in spec.boxes:
        bt = catalog.box_templates.get(box.template)
        if bt is None:
            problems.append(f"unknown box template: {box.template!r}")
        default_attachments = bt.default_attachments if bt else []
        # Validate template_vm resolves when 01_image_layer is loaded (optional layer).
        if bt is not None and catalog.images and find_template_vm(catalog, bt.template_vm) is None:
            problems.append(
                f"unknown template_vm {bt.template_vm!r} (box template {box.template!r})"
            )
        for att in list(default_attachments) + list(box.attachments_add):
            if att.kind == "role" and att.catalog_ref not in catalog.roles:
                problems.append(f"unknown role: {att.catalog_ref!r}")
            elif att.kind == "container" and att.catalog_ref not in catalog.containers:
                problems.append(f"unknown container: {att.catalog_ref!r}")
    if spec.services is not None and spec.services.apt is not None:
        apt_svc = spec.services.apt
        box_templates = {b.template for b in spec.boxes}
        if apt_svc.box not in box_templates:
            problems.append(
                f"services.apt.box {apt_svc.box!r} is not in spec boxes"
            )
        if isinstance(apt_svc.wire_to, list):
            for ref in apt_svc.wire_to:
                if ref not in box_templates:
                    problems.append(
                        f"services.apt.wire_to ref {ref!r} is not in spec boxes"
                    )
        if "software.configure.apt_mirror_client" not in catalog.roles:
            problems.append("unknown role: 'software.configure.apt_mirror_client'")
    return problems
