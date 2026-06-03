"""P2 id/IP allocation + reservation tests — RED before GREEN."""

from r42topo.core.idalloc import ReservedIndex, validate_allocation
from r42topo.core.models import Topology


def test_valid_topology_has_no_allocation_errors(valid_topology_dict, reserved_factory):
    t = Topology.model_validate(valid_topology_dict)
    reserved = ReservedIndex.from_file(reserved_factory([]))
    report = validate_allocation(t, reserved)
    assert report.errors == []


def test_octet_rule_violation_is_error(topology_factory, reserved_factory):
    spec = topology_factory()
    spec["boxes"][0]["vm_id"] = 1101  # ip ends .100 -> 101 != 100
    t = Topology.model_validate(spec)
    report = validate_allocation(t, ReservedIndex.from_file(reserved_factory([])))
    assert any("octet" in e.lower() for e in report.errors)


def test_cross_scenario_vm_id_collision_is_error(valid_topology_dict, reserved_factory):
    t = Topology.model_validate(valid_topology_dict)
    reserved = ReservedIndex.from_file(reserved_factory([
        {"vm_id": 1100, "ip": "192.168.1.1", "scenario": "other_lab", "role": "admin"},
    ]))
    report = validate_allocation(t, reserved)
    assert any("1100" in e and "other_lab" in e for e in report.errors)


def test_same_scenario_reservation_is_not_collision(valid_topology_dict, reserved_factory):
    t = Topology.model_validate(valid_topology_dict)  # scenario demo_lab_network
    reserved = ReservedIndex.from_file(reserved_factory([
        {"vm_id": 1100, "ip": "192.168.142.100", "scenario": "demo_lab_network", "role": "admin"},
    ]))
    report = validate_allocation(t, reserved)
    assert report.errors == []  # re-deploy of own scenario is fine


def test_cross_scenario_ip_collision_is_error(valid_topology_dict, reserved_factory):
    t = Topology.model_validate(valid_topology_dict)
    reserved = ReservedIndex.from_file(reserved_factory([
        {"vm_id": 5555, "ip": "192.168.142.100", "scenario": "other_lab", "role": "admin"},
    ]))
    report = validate_allocation(t, reserved)
    assert any("192.168.142.100" in e and "other_lab" in e for e in report.errors)


def test_intra_topology_duplicate_vm_id_is_error(topology_factory, reserved_factory):
    spec = topology_factory()
    spec["boxes"][1]["vm_id"] = spec["boxes"][0]["vm_id"]  # dup within topology
    spec["boxes"][1]["ip"] = "192.168.144." + str(spec["boxes"][0]["vm_id"] % 1000)
    t = Topology.model_validate(spec)
    report = validate_allocation(t, ReservedIndex.from_file(reserved_factory([])))
    assert any("duplicate" in e.lower() for e in report.errors)


def test_reserved_index_parses_jsonl(reserved_factory):
    reserved = ReservedIndex.from_file(reserved_factory([
        {"vm_id": 2001, "ip": "192.168.143.200", "scenario": "a", "role": "team"},
        {"vm_id": 2002, "ip": "192.168.143.201", "scenario": "a", "role": "team"},
    ]))
    assert reserved.used_vm_ids() == {2001, 2002}
    assert "192.168.143.200" in reserved.used_ips()
