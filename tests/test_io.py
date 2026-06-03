"""P1 IO round-trip tests for r42topo.core.io — RED before GREEN."""

import json

from r42topo.core.io import dump_topology, load_topology
from r42topo.core.models import Topology


def test_round_trip_preserves_topology(tmp_path, valid_topology_dict):
    t = Topology.model_validate(valid_topology_dict)
    path = tmp_path / "topology.json"
    dump_topology(t, path)
    loaded = load_topology(path)
    assert loaded == t


def test_dump_writes_sorted_deterministic_json(tmp_path, valid_topology_dict):
    t = Topology.model_validate(valid_topology_dict)
    p1, p2 = tmp_path / "a.json", tmp_path / "b.json"
    dump_topology(t, p1)
    dump_topology(t, p2)
    assert p1.read_text() == p2.read_text()  # byte-identical
    top = json.loads(p1.read_text())
    assert list(top.keys()) == sorted(top.keys())  # sorted keys


def test_load_rejects_unknown_path(tmp_path):
    import pytest

    from r42topo.core.errors import TopologyError
    with pytest.raises(TopologyError):
        load_topology(tmp_path / "does-not-exist.json")
