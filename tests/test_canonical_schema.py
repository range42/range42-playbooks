"""Phase 1 (convergence): the generated canonical models accept every real fixture.

These are the SHARED test-vectors from range42-deployer-ui/schema (the source of
truth, also driving the TS + backend parity suites). If r42topo is to become the
shared topology engine, its models must validate exactly these documents.

A scenario/topology document is a `CatalogEntry`; a project overlay is a
`ProjectOverlay` (compose input). This module only asserts schema acceptance +
round-trip; the operators (compose / expand_replication / redaction) land in the
following phases against the same vectors.
"""

import json
from pathlib import Path

import pytest

from r42topo.core.canonical import CatalogEntry, ProjectOverlay

VECTORS = Path(__file__).parent / "vectors" / "test-vectors"


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# --- raw topology docs are CatalogEntry ---

@pytest.mark.parametrize("path", sorted((VECTORS / "topology").glob("*.json")), ids=lambda p: p.name)
def test_topology_vectors_are_catalog_entries(path):
    doc = _load(path)
    entry = CatalogEntry.model_validate(doc)
    assert entry.kind is not None and entry.name
    # re-dump must re-validate (round-trip stability)
    CatalogEntry.model_validate(entry.model_dump(mode="json", by_alias=True))


# --- serialize vectors: `input` is the UI canvas form (a UI/TS concern); the
# Python engine consumes the serialized `expected` document (a CatalogEntry).
# sample-projects/ are canvas-form too, so they are NOT r42topo's input. ---

@pytest.mark.parametrize("path", sorted((VECTORS / "serialize").glob("*.json")), ids=lambda p: p.name)
def test_serialize_expected_is_catalog_entry(path):
    v = _load(path)
    CatalogEntry.model_validate(v["expected"])
    # the input is the canvas representation, deliberately NOT a CatalogEntry
    assert "canvas" in v["input"] or "nodes" not in v["input"]


# --- compose vectors: input.base = CatalogEntry, input.overlay = ProjectOverlay, expected = CatalogEntry ---

@pytest.mark.parametrize("path", sorted((VECTORS / "compose").glob("*.json")), ids=lambda p: p.name)
def test_compose_vector_docs_validate(path):
    v = _load(path)
    CatalogEntry.model_validate(v["input"]["base"])
    ProjectOverlay.model_validate(v["input"]["overlay"])
    CatalogEntry.model_validate(v["expected"])


# --- expand_replication vectors: input.document = CatalogEntry ---

@pytest.mark.parametrize("path", sorted((VECTORS / "expand_replication").glob("*.json")), ids=lambda p: p.name)
def test_expand_replication_input_doc_validates(path):
    v = _load(path)
    CatalogEntry.model_validate(v["input"]["document"])
    assert isinstance(v["input"]["team_count"], int)
