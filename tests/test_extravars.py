"""P3 extravars tests — RED before GREEN."""

import pytest

from r42topo.core.catalog import load_catalog
from r42topo.core.compiler import compile_topology
from r42topo.core.errors import ValidationError
from r42topo.core.extravars import resolve_universal_extravars
from r42topo.core.idalloc import ReservedIndex
from r42topo.core.models import Topology


@pytest.fixture
def result(topology_factory, fake_catalog, reserved_factory, tmp_path):
    t = Topology.model_validate(topology_factory())
    cat = load_catalog(fake_catalog)
    reserved = ReservedIndex.from_file(reserved_factory([]))
    return compile_topology(t, workspace=tmp_path / "ws", catalog=cat, reserved=reserved)


def test_extravars_has_universal_contract_keys(result):
    ev = resolve_universal_extravars(result, deployment_id="dep-1", attempt_id="att-1",
                                     scope="team", team_id="team-a")
    assert set(ev) == {
        "r42_topology_path", "r42_inventory_dir", "r42_deployment_id",
        "r42_attempt_id", "r42_scope", "r42_team_id",
    }
    assert ev["r42_topology_path"] == str(result.topology_path)
    assert ev["r42_inventory_dir"] == str(result.workspace / "inventory")
    assert ev["r42_team_id"] == "team-a"


def test_extravars_team_id_optional(result):
    ev = resolve_universal_extravars(result, deployment_id="d", attempt_id="a", scope="global")
    assert ev["r42_team_id"] == ""


def test_extravars_rejects_injection_in_ids(result):
    with pytest.raises(ValidationError):
        resolve_universal_extravars(result, deployment_id="d;rm -rf /", attempt_id="a",
                                    scope="global")


def test_extravars_only_allowlisted_keys(result):
    # no ansible_* or arbitrary keys can leak through
    ev = resolve_universal_extravars(result, deployment_id="d", attempt_id="a", scope="global")
    assert not any(k.lower().startswith("ansible") for k in ev)
