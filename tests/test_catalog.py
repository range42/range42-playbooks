"""P2 catalog loader tests — RED before GREEN."""

import pytest

from r42playbooks.core.catalog import list_images, load_catalog
from r42playbooks.core.errors import CatalogNotFoundError


def test_load_catalog_indexes_all_categories(fake_catalog):
    cat = load_catalog(fake_catalog)
    assert set(cat.box_templates) == {"vuln-box", "admin-wazuh", "student-box"}
    assert set(cat.network_policies) == {"air-gap-ctf"}
    assert set(cat.subnet_layouts) == {"default-3zone"}
    assert set(cat.images) == {"ubuntu_noble", "debian_trixie"}


def test_box_template_fields_parsed(fake_catalog):
    cat = load_catalog(fake_catalog)
    vb = cat.box_templates["vuln-box"]
    assert vb.default_attachments[0].catalog_ref == "software.install.wazuh-agent"


def test_loader_picks_highest_version(fake_catalog):
    cat = load_catalog(fake_catalog)
    pol = cat.network_policies["air-gap-ctf"]
    assert cat.resolved_version("network_policies", "air-gap-ctf") == "1.1.0"
    # content hash is recorded for reproducibility
    assert len(cat.resolved_hash("network_policies", "air-gap-ctf")) == 64


def test_network_policy_structure(fake_catalog):
    cat = load_catalog(fake_catalog)
    pol = cat.network_policies["air-gap-ctf"]
    assert pol.kind == "isolation-policy"
    assert {z.name for z in pol.zones} == {"admin", "ctf", "wan"}
    assert any(z.wan for z in pol.zones)
    assert pol.defaults.airgap_zones == ["ctf"]
    assert any(r.dst == "svc:siem" for r in pol.matrix)


def test_resolve_helpers(fake_catalog):
    cat = load_catalog(fake_catalog)
    assert cat.resolve_box_template("vuln-box").id == "vuln-box"
    assert cat.resolve_network_policy("air-gap-ctf").id == "air-gap-ctf"


def test_missing_template_raises(fake_catalog):
    cat = load_catalog(fake_catalog)
    with pytest.raises(CatalogNotFoundError):
        cat.resolve_box_template("does-not-exist")


def test_missing_layer_raises(tmp_path):
    with pytest.raises(CatalogNotFoundError):
        load_catalog(tmp_path / "empty")


def test_template_id_traversal_rejected(fake_catalog):
    cat = load_catalog(fake_catalog)
    with pytest.raises(CatalogNotFoundError):
        cat.resolve_box_template("../../etc/passwd")


def test_shipped_catalog_validates():
    """The real range42-catalog (sibling repo) must load if present."""
    from pathlib import Path
    sibling = Path(__file__).resolve().parents[2] / "range42-catalog"
    if not (sibling / "05_topology_layer").is_dir():
        pytest.skip("range42-catalog sibling not checked out")
    cat = load_catalog(sibling)
    assert cat.box_templates and cat.network_policies and cat.subnet_layouts
    assert cat.images, "01_image_layer must be present in the shipped catalog"


def test_image_fields_parsed(fake_catalog):
    cat = load_catalog(fake_catalog)
    noble = cat.images["ubuntu_noble"]
    assert noble.distro == "ubuntu"
    assert noble.codename == "noble"
    trixie = cat.images["debian_trixie"]
    assert trixie.distro == "debian"
    assert trixie.codename == "trixie"


def test_image_layer_absent_is_ok(tmp_path):
    """load_catalog succeeds when 01_image_layer is absent — layer is optional."""
    from pathlib import Path
    # Minimal catalog with only the topology layer
    layer = tmp_path / "cat" / "05_topology_layer"
    (layer / "subnet_layouts" / "s" / "v1.0.0").mkdir(parents=True)
    (layer / "subnet_layouts" / "s" / "v1.0.0" / "template.yml").write_text(
        "id: s\napi_version: 1\ndescription: x\nsubnets:\n  - {name: a, cidr: 10.0.0.0/24, bridge: vmbr0}\n"
    )
    cat = load_catalog(tmp_path / "cat")
    assert cat.images == {}


def test_list_images(fake_catalog):
    imgs = list_images(fake_catalog)
    assert imgs == ["debian_trixie", "ubuntu_noble"]  # sorted


def test_list_images_absent_returns_empty(tmp_path):
    assert list_images(tmp_path / "empty") == []
