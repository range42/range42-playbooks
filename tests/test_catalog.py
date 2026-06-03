"""P2 catalog loader tests — RED before GREEN."""

import pytest

from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.errors import CatalogNotFoundError


def test_load_catalog_indexes_all_categories(fake_catalog):
    cat = load_catalog(fake_catalog)
    assert set(cat.box_templates) == {"vuln-box", "admin-wazuh"}
    assert set(cat.network_policies) == {"air-gap-ctf"}
    assert set(cat.subnet_layouts) == {"default-3zone"}


def test_box_template_fields_parsed(fake_catalog):
    cat = load_catalog(fake_catalog)
    vb = cat.box_templates["vuln-box"]
    assert vb.role == "ctf"
    assert vb.default_inventory_group == "r42_vuln_box_group"
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
    """The real range42-catalog/05_topology_layer (sibling repo) must load if present."""
    from pathlib import Path
    sibling = Path(__file__).resolve().parents[2] / "range42-catalog"
    if not (sibling / "05_topology_layer").is_dir():
        pytest.skip("range42-catalog sibling not checked out")
    cat = load_catalog(sibling)
    assert cat.box_templates and cat.network_policies and cat.subnet_layouts
