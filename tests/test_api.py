"""Canonical api adapter surface (r42topo.api) over the shared test-vectors."""
import json
from pathlib import Path

import pytest

from r42topo import api
from r42topo.core.canonical import CatalogEntry
from r42topo.core.errors import ValidationError

VECTORS = Path(__file__).parent / "vectors" / "test-vectors"


def _topo(name: str) -> dict:
    return json.loads((VECTORS / "topology" / f"{name}.json").read_text(encoding="utf-8"))


def test_load_and_validate_document(tmp_path):
    doc = _topo("01-minimal")
    p = tmp_path / "topo.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    loaded = api.load_document(p)
    entry = api.validate_document(loaded)
    assert isinstance(entry, CatalogEntry)
    assert entry.kind.value == "gamenet"


def test_validate_document_rejects_garbage():
    with pytest.raises(ValidationError, match="invalid topology"):
        api.validate_document({"kind": "not-a-kind", "name": 123})


def test_validate_document_rejects_injection_in_config():
    doc = {
        "schema_version": "1.0", "kind": "gamenet", "name": "x", "naming_prefix": "x",
        "nodes": [
            {"id": "n", "kind": "vm", "role": "admin",
             "replication": {"scope": "shared"}, "template_vmid": 5000,
             "config": {"hostname": "{{ lookup('pipe','id') }}"}},
        ],
    }
    with pytest.raises(ValidationError, match="forbidden values"):
        api.validate_document(doc)


def test_assert_document_safe_passes_clean_and_flags_dirty():
    api.assert_document_safe(_topo("01-minimal"))  # clean → no raise
    with pytest.raises(ValidationError, match="config"):
        api.assert_document_safe({
            "kind": "gamenet", "name": "x",
            "nodes": [{"id": "n", "kind": "vm", "config": {"c": "a;b"}}],
        })


def test_validate_overlay_on_compose_vector():
    v = json.loads((VECTORS / "compose" / "01_identity.json").read_text(encoding="utf-8"))
    overlay = api.validate_overlay(v["input"]["overlay"])
    assert overlay.source_sha


def test_compose_effective_returns_doc_and_stable_hash():
    v = json.loads((VECTORS / "compose" / "02_nodes_added.json").read_text(encoding="utf-8"))
    eff, h = api.compose_effective(v["input"]["base"], v["input"]["overlay"])
    assert eff == v["expected"]
    assert h.startswith("sha256:")
    # recompute is stable
    assert api.compose_effective(v["input"]["base"], v["input"]["overlay"])[1] == h


def test_validate_overlay_rejects_garbage():
    with pytest.raises(ValidationError, match="invalid project overlay"):
        api.validate_overlay({"schema_version": "1.0"})  # missing source_url/source_sha


def test_compose_effective_rejects_overlay_injection():
    # an injection smuggled via param_overrides lands in the effective doc and
    # must be caught by the post-compose deny-list scan
    base = _topo("01-minimal")
    overlay = {
        "schema_version": "1.0",
        "source_url": "https://github.com/me/repo.git",
        "source_sha": "deadbeef",
        "param_overrides": {"defaults.hostname": "a;rm -rf /"},
    }
    with pytest.raises(ValidationError, match="forbidden values"):
        api.compose_effective(base, overlay)


def test_compose_effective_identity_without_overlay():
    base = _topo("01-minimal")
    eff, _ = api.compose_effective(base, None)
    assert eff == base


def test_expand_replication_multi_team():
    doc = _topo("02-multi-team")
    result = api.expand_replication(doc, 3)
    assert result["plays_per_team"] == 3


def test_write_inventory_smoke(tmp_path):
    doc = _topo("02-multi-team")
    dest = tmp_path / "hosts.yml"
    out = api.write_inventory(
        topology=doc, team_count=2, codename="MT",
        proxmox_address="10.0.0.1", ssh_keys_dir=tmp_path / "keys", dest=dest,
    )
    assert out == dest and dest.exists()


def test_preflight_document_passes_for_clean_topology():
    # NOTE: the ported check_vmid_safety_for_topology uses template_vmid as the
    # allocation base (the canonical schema has no vmid_base), so the safe case
    # must keep template_vmid out of the 9000-9999 protected range. The shared
    # 02-multi-team vector uses 9001/9020 templates and so blocks — a faithful
    # backend quirk flagged for spec reconciliation, not changed here.
    doc = {
        "schema_version": "1.0", "kind": "gamenet", "name": "x", "naming_prefix": "x",
        "nodes": [
            {"id": "adm", "kind": "vm", "role": "admin",
             "replication": {"scope": "shared"}, "template_vmid": 5000},
            {"id": "tr", "kind": "vm", "role": "team",
             "replication": {"scope": "per_team"}, "template_vmid": 5100},
        ],
    }
    report = api.preflight_document(doc, team_count=2)
    assert report.result == "pass", [(c.check, c.result, c.detail) for c in report.checks]


def test_preflight_document_blocks_protected_vmid():
    # template_vmid in the protected 9000-9999 band (schema-valid, unlike the
    # non-canonical vmid_base) — see the base-field note above.
    doc = {
        "schema_version": "1.0", "kind": "gamenet", "name": "x", "naming_prefix": "x",
        "nodes": [
            {"id": "bad", "kind": "vm", "role": "admin",
             "replication": {"scope": "shared"}, "template_vmid": 9001},  # protected
        ],
    }
    report = api.preflight_document(doc, team_count=1)
    assert report.result == "block"


def test_preflight_document_blocks_missing_role():
    doc = {
        "schema_version": "1.0", "kind": "gamenet", "name": "x", "naming_prefix": "x",
        "nodes": [
            {"id": "norole", "kind": "vm", "replication": {"scope": "shared"},
             "template_vmid": 8000},
        ],
    }
    report = api.preflight_document(doc, team_count=1)
    assert report.result == "block"
