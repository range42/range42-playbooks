"""P3 importable-API adapter tests (the surface FastAPI / deployment CLI call)."""

import pytest

from r42playbooks import api
from r42playbooks.core.errors import ValidationError
from r42playbooks.core.idalloc import ReservedIndex
from r42playbooks.core.models import Topology


def test_load_catalog_reexported(fake_catalog):
    cat = api.load_catalog(fake_catalog)
    assert "vuln-box" in cat.box_templates


def test_author_topology_returns_model(topology_factory, fake_catalog):
    cat = api.load_catalog(fake_catalog)
    t = api.author_topology(topology_factory(), catalog=cat)
    assert isinstance(t, Topology)


def test_author_topology_rejects_dangling_ref(topology_factory, fake_catalog):
    cat = api.load_catalog(fake_catalog)
    spec = topology_factory()
    spec["boxes"][0]["box_template"] = "missing-template"
    with pytest.raises(ValidationError):
        api.author_topology(spec, catalog=cat)


def test_validate_topology_clean(topology_factory, fake_catalog, reserved_factory):
    cat = api.load_catalog(fake_catalog)
    t = Topology.model_validate(topology_factory())
    reserved = ReservedIndex.from_file(reserved_factory([]))
    assert api.validate_topology(t, catalog=cat, reserved=reserved) == []


def test_validate_topology_reports_problems(topology_factory, fake_catalog, reserved_factory):
    cat = api.load_catalog(fake_catalog)
    spec = topology_factory()
    spec["boxes"][0]["ip"] = "10.0.0.100"
    t = Topology.model_validate(spec)
    reserved = ReservedIndex.from_file(reserved_factory([]))
    assert api.validate_topology(t, catalog=cat, reserved=reserved)


def test_full_author_compile_extravars(topology_factory, fake_catalog, reserved_factory, tmp_path):
    cat = api.load_catalog(fake_catalog)
    reserved = ReservedIndex.from_file(reserved_factory([]))
    t = api.author_topology(topology_factory(), catalog=cat)
    assert api.validate_topology(t, catalog=cat, reserved=reserved) == []
    result = api.compile_topology(t, workspace=tmp_path / "ws", catalog=cat, reserved=reserved)
    ev = api.resolve_universal_extravars(result, deployment_id="d", attempt_id="a", scope="global")
    # the _universal stub asserts this path exists and is a regular file
    from pathlib import Path
    assert Path(ev["r42_topology_path"]).is_file()
