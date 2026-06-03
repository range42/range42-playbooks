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

import yaml

from r42topo.core import constants as C
from r42topo.core.catalog_models import (
    BoxTemplate,
    NetworkPolicyTemplate,
    SubnetLayout,
)
from r42topo.core.errors import CatalogNotFoundError, ValidationError

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
    """In-memory index of validated topology-layer templates."""

    box_templates: dict[str, BoxTemplate] = field(default_factory=dict)
    network_policies: dict[str, NetworkPolicyTemplate] = field(default_factory=dict)
    subnet_layouts: dict[str, SubnetLayout] = field(default_factory=dict)
    _resolved: dict[tuple[str, str], _Resolved] = field(default_factory=dict)

    # -- resolution helpers (raise CatalogNotFoundError on miss) --

    def resolve_box_template(self, ref: str) -> BoxTemplate:
        return self._resolve(C.CATEGORY_BOX_TEMPLATES, ref, self.box_templates)

    def resolve_network_policy(self, ref: str) -> NetworkPolicyTemplate:
        return self._resolve(C.CATEGORY_NETWORK_POLICIES, ref, self.network_policies)

    def resolve_subnet_layout(self, ref: str) -> SubnetLayout:
        return self._resolve(C.CATEGORY_SUBNET_LAYOUTS, ref, self.subnet_layouts)

    def resolved_version(self, category: str, template_id: str) -> str:
        return self._resolved[(category, template_id)].version

    def resolved_hash(self, category: str, template_id: str) -> str:
        return self._resolved[(category, template_id)].sha256

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
        except Exception as exc:  # pydantic ValidationError -> our ValidationError
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


def load_catalog(catalog_root: Path) -> Catalog:
    """Load + validate all topology-layer templates from a catalog checkout.

    :param catalog_root: path that contains ``05_topology_layer/``.
    :raises CatalogNotFoundError: if the layer dir is absent.
    :raises ValidationError: if any template file fails schema validation.
    """
    layer_root = (Path(catalog_root) / C.TOPOLOGY_LAYER_DIR).resolve()
    if not layer_root.is_dir():
        raise CatalogNotFoundError(f"missing {C.TOPOLOGY_LAYER_DIR} under {catalog_root}")

    catalog = Catalog()
    for category in _CATEGORY_MODEL:
        _load_category(layer_root, category, catalog)
    return catalog
