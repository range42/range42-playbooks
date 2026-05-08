import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from r42_topology import (
    r42_bridge_for_team, r42_subnet_for_team,
    r42_vmid_for_node, r42_ip_for_node,
    r42_expand_per_team, r42_attachments_for,
)


def test_bridge_for_team():
    assert r42_bridge_for_team(140, 0) == "vmbr140"
    assert r42_bridge_for_team(140, 3) == "vmbr143"


def test_subnet_for_team():
    assert r42_subnet_for_team(140, 0) == "192.168.140.0/24"
    assert r42_subnet_for_team(140, 5) == "192.168.145.0/24"


def test_vmid_for_node():
    assert r42_vmid_for_node(5000, 0, 0, 4) == 5000
    assert r42_vmid_for_node(5000, 1, 2, 4) == 5006
    assert r42_vmid_for_node(5000, 3, 0, 4) == 5012


def test_ip_for_node_per_team():
    assert r42_ip_for_node(140, 1, 0) == "192.168.141.200"
    assert r42_ip_for_node(140, 2, 5) == "192.168.142.205"


def test_ip_for_node_shared():
    assert r42_ip_for_node(140, None, 0) == "192.168.140.200"


def test_expand_per_team_shared_first():
    items = [
        {"id": "a", "replication": {"scope": "shared"}},
        {"id": "b", "replication": {"scope": "per_team"}},
    ]
    result = r42_expand_per_team(items, 2)
    assert len(result) == 3
    assert result[0] == {"team_id": None, "item": items[0]}
    assert result[1]["team_id"] == 1
    assert result[2]["team_id"] == 2


def test_expand_per_team_stable_ordering():
    items = [{"id": "z", "replication": {"scope": "shared"}},
             {"id": "a", "replication": {"scope": "shared"}}]
    r1 = r42_expand_per_team(items, 1)
    r2 = r42_expand_per_team(items, 1)
    assert r1 == r2
    assert r1[0]["item"]["id"] == "a"


def test_expand_per_team_handles_empty():
    assert r42_expand_per_team([], 2) == []
    assert r42_expand_per_team(None, 2) == []


def test_expand_per_team_handles_no_replication_field():
    """Defensive: items missing replication field treated as not-per-team."""
    items = [{"id": "x"}]
    result = r42_expand_per_team(items, 3)
    assert result == []  # neither shared nor per_team


def test_attachments_for_shared_node():
    topology = {
        "naming_prefix": "test",
        "nodes": [
            {"id": "n1", "kind": "vm", "replication": {"scope": "shared"},
             "attachments": [{"source": {"kind": "catalog_role", "ref": "x.y.z"}}]},
        ]
    }
    atts = r42_attachments_for(topology, "r42.test-n1")
    assert len(atts) == 1
    assert atts[0]["source"]["ref"] == "x.y.z"


def test_attachments_for_per_team_node():
    topology = {
        "naming_prefix": "test",
        "nodes": [
            {"id": "n1", "kind": "vm", "replication": {"scope": "per_team"},
             "attachments": [{"source": {"kind": "catalog_role", "ref": "x"}}]},
        ]
    }
    atts = r42_attachments_for(topology, "r42.test-2-n1")
    assert atts[0]["source"]["ref"] == "x"


def test_attachments_for_unknown_host():
    topology = {"naming_prefix": "test", "nodes": []}
    assert r42_attachments_for(topology, "r42.unknown") == []


def test_attachments_for_no_attachments():
    """Node exists but has empty/missing attachments[]."""
    topology = {
        "naming_prefix": "test",
        "nodes": [{"id": "n1", "kind": "vm"}],  # no attachments key
    }
    assert r42_attachments_for(topology, "r42.test-n1") == []


def test_attachments_for_multi_segment_name():
    """Node names with hyphens must still resolve."""
    topology = {
        "naming_prefix": "test",
        "nodes": [
            {"id": "host-with-hyphens", "kind": "vm",
             "replication": {"scope": "shared"},
             "attachments": [{"source": {"kind": "x", "ref": "y"}}]},
        ]
    }
    atts = r42_attachments_for(topology, "r42.test-host-with-hyphens")
    assert len(atts) == 1
