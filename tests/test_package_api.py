"""S8 — the importable package surface.

A downstream tool (r42deploy/r42runtime) must be able to drive generation by
``import r42playbooks`` alone, without reaching into ``r42playbooks.core`` or
``r42playbooks.api``. These tests pin that top-level re-export contract.
"""

import r42playbooks as r
from r42playbooks.core.errors import TopologyError


def test_package_exports_frozen_generator_surface():
    for name in (
        "render_scenario", "allocate", "load_spec", "dump_spec_atomic",
        "load_catalog", "list_roles", "list_containers", "validate_refs",
        "ScenarioSpec", "Catalog", "Allocation", "ReservedIndex", "__version__",
    ):
        assert hasattr(r, name), f"r42playbooks.{name} not exported"


def test_import_only_generation_roundtrip(fake_catalog, valid_spec_dict, tmp_path):
    spec = r.ScenarioSpec.model_validate(valid_spec_dict)
    catalog = r.load_catalog(fake_catalog)
    assert r.validate_refs(spec, catalog) == []
    root = r.render_scenario(spec, catalog=catalog, dest=tmp_path / "out")
    assert (root / "main.yml").is_file()
    assert (root / "manifest" / "scenario_vms.json").is_file()
    assert (root / "scenario.r42.yml").is_file()


def test_load_spec_then_render(fake_catalog, valid_spec_dict, tmp_path):
    import yaml
    spec_path = tmp_path / "scenario.r42.yml"
    spec_path.write_text(yaml.safe_dump(valid_spec_dict), encoding="utf-8")
    spec = r.load_spec(spec_path)
    catalog = r.load_catalog(fake_catalog)
    root = r.render_scenario(spec, catalog=catalog, dest=tmp_path / "out")
    assert root.is_dir()


def test_unknown_catalog_ref_raises_core_error(fake_catalog, spec_factory, tmp_path):
    bad = spec_factory(boxes=[{"template": "ghost-box"}])
    spec = r.ScenarioSpec.model_validate(bad)
    catalog = r.load_catalog(fake_catalog)
    # validate_refs surfaces it as a message...
    assert any("ghost-box" in p for p in r.validate_refs(spec, catalog))
    # ...and render raises the core error hierarchy (not a framework type)
    try:
        r.render_scenario(spec, catalog=catalog, dest=tmp_path / "out")
        raised = None
    except TopologyError as exc:
        raised = exc
    assert raised is not None
