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
