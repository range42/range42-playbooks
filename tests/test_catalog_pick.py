"""Step 3 — catalog pick/validate API (RED before GREEN).

Enumerate pickable roles (02_ansible_layer) and containers (03_container_layer),
and validate that every ref in a ScenarioSpec resolves in the catalog.
All tests use the fake_catalog fixture — the real range42-catalog is a separate,
gitignored repo never present in this checkout.
"""

from r42playbooks.core.catalog import (
    list_containers,
    list_roles,
    load_catalog,
    validate_refs,
)
from r42playbooks.core.spec import ScenarioSpec


def test_list_roles_enumerates_role_dir_names(fake_catalog):
    roles = list_roles(fake_catalog)
    assert "software.install.wazuh" in roles
    assert "software.install.wazuh-agent" in roles
    assert roles == sorted(roles)  # deterministic ordering


def test_list_containers_enumerates_ctf_paths(fake_catalog):
    containers = list_containers(fake_catalog)
    assert "cve/web/dvwa" in containers
    assert "misconfiguration/network/open-smb" in containers


def test_list_is_empty_when_layers_absent(tmp_path):
    # a catalog_root without 02/03 layers yields empty lists, not an error
    assert list_roles(tmp_path) == []
    assert list_containers(tmp_path) == []


def test_load_catalog_populates_roles_and_containers(fake_catalog):
    catalog = load_catalog(fake_catalog)
    assert "software.install.wazuh" in catalog.roles
    assert "cve/web/dvwa" in catalog.containers


def test_validate_refs_all_known_returns_empty(fake_catalog, valid_spec_dict):
    catalog = load_catalog(fake_catalog)
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    assert validate_refs(spec, catalog) == []


def test_validate_refs_reports_unknown_box_template(fake_catalog, spec_factory):
    catalog = load_catalog(fake_catalog)
    data = spec_factory(boxes=[{"template": "ghost-box"}])
    spec = ScenarioSpec.model_validate(data)
    problems = validate_refs(spec, catalog)
    assert any("ghost-box" in p for p in problems)


def test_validate_refs_reports_unknown_subnet_and_policy(fake_catalog, spec_factory):
    catalog = load_catalog(fake_catalog)
    data = spec_factory(subnet_layout="nope-layout", network_policy="nope-policy")
    spec = ScenarioSpec.model_validate(data)
    problems = validate_refs(spec, catalog)
    assert any("nope-layout" in p for p in problems)
    assert any("nope-policy" in p for p in problems)


def test_validate_refs_reports_unknown_role(fake_catalog, valid_spec_dict):
    catalog = load_catalog(fake_catalog)
    valid_spec_dict["boxes"][0]["attachments_add"] = [
        {"kind": "role", "catalog_ref": "software.install.ghost", "params": {}},
    ]
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    problems = validate_refs(spec, catalog)
    assert any("software.install.ghost" in p for p in problems)


def test_validate_refs_reports_unknown_container(fake_catalog, valid_spec_dict):
    catalog = load_catalog(fake_catalog)
    valid_spec_dict["boxes"][0]["attachments_add"] = [
        {"kind": "container", "catalog_ref": "cve/web/ghost", "params": {}},
    ]
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    problems = validate_refs(spec, catalog)
    assert any("cve/web/ghost" in p for p in problems)


def test_validate_refs_accepts_known_role_and_container(fake_catalog, valid_spec_dict):
    catalog = load_catalog(fake_catalog)
    valid_spec_dict["boxes"][0]["attachments_add"] = [
        {"kind": "role", "catalog_ref": "software.install.wazuh", "params": {}},
        {"kind": "container", "catalog_ref": "cve/web/dvwa", "params": {}},
    ]
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    assert validate_refs(spec, catalog) == []
