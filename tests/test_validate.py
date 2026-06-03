"""P3 semantic validation tests — RED before GREEN."""

from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.models import Topology
from r42playbooks.core.validate import semantic_problems


def _valid(topology_factory, fake_catalog):
    return Topology.model_validate(topology_factory()), load_catalog(fake_catalog)


def test_valid_topology_has_no_semantic_problems(topology_factory, fake_catalog):
    t, cat = _valid(topology_factory, fake_catalog)
    assert semantic_problems(t, cat) == []


def test_box_zone_must_exist(topology_factory, fake_catalog):
    spec = topology_factory()
    spec["boxes"][0]["zone"] = "ghost"
    t = Topology.model_validate(spec)
    probs = semantic_problems(t, load_catalog(fake_catalog))
    assert any("ghost" in p for p in probs)


def test_zone_subnet_must_exist(topology_factory, fake_catalog):
    spec = topology_factory()
    spec["zones"][0]["subnet"] = "nope"
    t = Topology.model_validate(spec)
    probs = semantic_problems(t, load_catalog(fake_catalog))
    assert any("nope" in p for p in probs)


def test_box_ip_must_be_in_zone_subnet(topology_factory, fake_catalog):
    spec = topology_factory()
    spec["boxes"][0]["ip"] = "10.0.0.100"  # not in 192.168.142.0/24
    spec["boxes"][0]["vm_id"] = 1100  # keep octet rule happy (.100)
    t = Topology.model_validate(spec)
    probs = semantic_problems(t, load_catalog(fake_catalog))
    assert any("10.0.0.100" in p for p in probs)


def test_dangling_box_template_is_problem(topology_factory, fake_catalog):
    spec = topology_factory()
    spec["boxes"][0]["box_template"] = "missing-template"
    t = Topology.model_validate(spec)
    probs = semantic_problems(t, load_catalog(fake_catalog))
    assert any("missing-template" in p for p in probs)


def test_dangling_network_policy_is_problem(topology_factory, fake_catalog):
    spec = topology_factory()
    spec["network_policy"]["template"] = "no-such-policy"
    t = Topology.model_validate(spec)
    probs = semantic_problems(t, load_catalog(fake_catalog))
    assert any("no-such-policy" in p for p in probs)
