"""P1 schema tests for r42playbooks.core.models — RED before GREEN."""

import pytest
from pydantic import ValidationError

from r42playbooks.core.models import Topology


def test_valid_topology_parses(valid_topology_dict):
    t = Topology.model_validate(valid_topology_dict)
    assert t.scenario == "demo_lab_network"
    assert len(t.boxes) == 2
    assert t.network_policy.template == "air-gap-ctf"


def test_scenario_name_rejects_dots(topology_factory):
    # backend resolver regex forbids dots in scenario names
    with pytest.raises(ValidationError):
        Topology.model_validate(topology_factory(scenario="demo.lab"))


def test_scenario_name_rejects_leading_slash(topology_factory):
    with pytest.raises(ValidationError):
        Topology.model_validate(topology_factory(scenario="/demo_lab"))


def test_bridge_pattern_enforced(topology_factory):
    spec = topology_factory()
    spec["subnets"][0]["bridge"] = "br0"  # not vmbrN
    with pytest.raises(ValidationError):
        Topology.model_validate(spec)


def test_vm_id_range_enforced(topology_factory):
    spec = topology_factory()
    spec["boxes"][0]["vm_id"] = 99  # below 1000
    with pytest.raises(ValidationError):
        Topology.model_validate(spec)


def test_extra_fields_forbidden(topology_factory):
    with pytest.raises(ValidationError):
        Topology.model_validate(topology_factory(unexpected="x"))


def test_attachment_catalog_ref_allows_dots(valid_topology_dict):
    # role names like software.install.wazuh contain dots (unlike scenario names)
    t = Topology.model_validate(valid_topology_dict)
    assert t.boxes[0].attachments[0].catalog_ref == "software.install.wazuh"


@pytest.mark.parametrize("bad", [
    "{{ lookup('pipe','id') }}",
    "name;rm -rf /",
    "a|b",
    "../escape",
])
def test_denylist_rejects_injection_in_vm_name(topology_factory, bad):
    spec = topology_factory()
    spec["boxes"][0]["vm_name"] = bad
    with pytest.raises(ValidationError):
        Topology.model_validate(spec)
