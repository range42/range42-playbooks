"""Phase 3 (convergence): compose parity against the shared vectors.

compose(base, overlay) -> effective_document, matched against each compose
test-vector's `expected`. Full-document equality (these vectors carry a
complete expected doc).
"""

import json
from pathlib import Path

import pytest

from r42topo.core.overlay import compose

VECTORS = Path(__file__).parent / "vectors" / "test-vectors" / "compose"


@pytest.mark.parametrize("path", sorted(VECTORS.glob("*.json")), ids=lambda p: p.name)
def test_compose_matches_vector(path):
    v = json.loads(path.read_text(encoding="utf-8"))
    result = compose(v["input"]["base"], v["input"]["overlay"])
    assert result == v["expected"], f"{path.name}: composed doc mismatch"


def _base() -> dict:
    return {
        "schema_version": "1.0", "kind": "gamenet", "name": "b", "naming_prefix": "b",
        "defaults": {"region": "eu"},
        "nodes": [
            {"id": "a", "kind": "vm", "role": "admin", "config": {"cores": 1}},
            {"id": "grp", "kind": "group", "children": [
                {"id": "c", "kind": "vm", "role": "team", "config": {"cores": 2}},
            ]},
        ],
    }


def test_compose_param_overrides_dotted_and_node_addressing():
    eff = compose(_base(), {
        "param_overrides": {"defaults.region": "us", "nodes.a.config.cores": 8},
    })
    assert eff["defaults"]["region"] == "us"
    a = next(n for n in eff["nodes"] if n["id"] == "a")
    assert a["config"]["cores"] == 8


def test_compose_nodes_removed_top_level_and_in_group():
    eff = compose(_base(), {"nodes_removed": ["a", "c"]})
    ids = [n["id"] for n in eff["nodes"]]
    assert "a" not in ids
    grp = next(n for n in eff["nodes"] if n["id"] == "grp")
    assert grp["children"] == []


def test_compose_nodes_patched_shallow_merge():
    eff = compose(_base(), {"nodes_patched": [{"id": "a", "patch": {"role": "trainee"}}]})
    a = next(n for n in eff["nodes"] if n["id"] == "a")
    assert a["role"] == "trainee"


def test_compose_attachments_added_to_target_node():
    eff = compose(_base(), {
        "attachments_added": [
            {"target_node": "c", "source": {"kind": "catalog_role", "ref": "x"}, "stage": "install"},
        ],
    })
    grp = next(n for n in eff["nodes"] if n["id"] == "grp")
    c = grp["children"][0]
    assert c["attachments"][0]["source"]["ref"] == "x"
    assert "target_node" not in c["attachments"][0]  # stripped on insert


def test_compose_execution_override():
    eff = compose(_base(), {"execution_override": {"stages": ["init", "install"]}})
    assert eff["execution"] == {"stages": ["init", "install"]}


def test_compose_identity_when_no_overlay():
    base = {"schema_version": "1.0", "kind": "gamenet", "name": "x", "nodes": []}
    assert compose(base, None) == base


def test_compose_is_pure():
    base = {"schema_version": "1.0", "kind": "gamenet", "name": "x",
            "nodes": [{"id": "a", "kind": "vm"}]}
    overlay = {"nodes_added": [{"id": "b", "kind": "vm"}]}
    before = json.dumps(base, sort_keys=True)
    compose(base, overlay)
    assert json.dumps(base, sort_keys=True) == before  # base not mutated
