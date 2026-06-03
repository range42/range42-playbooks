"""Phase 2 (convergence): expand_replication parity against the shared vectors.

Runs the operator on each `expand_replication` test-vector and asserts the
result matches `expected`. Vectors may carry a partial `expected` (e.g. the
edge vector omits `document`); we assert subset-equality on the keys present,
matching the shared TS/Python parity harness.
"""

import json
from pathlib import Path

import pytest

from r42topo.core.overlay import expand_replication

VECTORS = Path(__file__).parent / "vectors" / "test-vectors" / "expand_replication"


@pytest.mark.parametrize("path", sorted(VECTORS.glob("*.json")), ids=lambda p: p.name)
def test_expand_replication_matches_vector(path):
    v = json.loads(path.read_text(encoding="utf-8"))
    result = expand_replication(v["input"]["document"], v["input"]["team_count"])
    for key, want in v["expected"].items():  # subset match (edge vectors omit keys)
        assert result[key] == want, f"{path.name}: key {key!r} mismatch"


def test_expand_replication_rejects_zero_teams():
    with pytest.raises(ValueError):
        expand_replication({"nodes": []}, 0)


def test_expand_replication_is_pure():
    doc = {"schema_version": "1.0", "kind": "gamenet", "name": "x",
           "nodes": [{"id": "n", "kind": "vm", "replication": {"scope": "per_team"},
                      "config": {"name_template": "t{team_id}"}}]}
    before = json.dumps(doc, sort_keys=True)
    expand_replication(doc, 2)
    assert json.dumps(doc, sort_keys=True) == before  # input not mutated
