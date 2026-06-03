"""Canonical JSON IO: load, deterministic dump, atomic write, effective hash."""
import json

import pytest

from r42topo.core.errors import TopologyError
from r42topo.core.io import (
    dump_json_atomic,
    dumps_canonical,
    effective_doc_hash,
    load_json,
)


def test_load_json_roundtrip(tmp_path):
    doc = {"kind": "gamenet", "nodes": [{"id": "a"}]}
    p = tmp_path / "doc.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert load_json(p) == doc


def test_load_json_missing_file_raises(tmp_path):
    with pytest.raises(TopologyError, match="cannot read"):
        load_json(tmp_path / "nope.json")


def test_load_json_invalid_json_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(TopologyError, match="invalid JSON"):
        load_json(p)


def test_dumps_canonical_is_sorted_and_newline_terminated():
    text = dumps_canonical({"b": 1, "a": 2})
    assert text.endswith("\n")
    assert text.index('"a"') < text.index('"b"')  # keys sorted


def test_dump_json_atomic_writes_and_leaves_no_tmp(tmp_path):
    dest = tmp_path / "out" / "doc.json"
    returned = dump_json_atomic({"a": 1}, dest)
    assert returned == dest
    assert load_json(dest) == {"a": 1}
    # no leftover temp files in the destination directory
    assert [p.name for p in dest.parent.iterdir()] == ["doc.json"]


def test_dump_text_atomic_cleans_up_temp_on_write_failure(tmp_path, monkeypatch):
    from r42topo.core import io

    dest = tmp_path / "out.txt"

    class _Boom:
        def write(self, *_a):
            raise OSError("disk full")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(io.os, "fdopen", lambda *a, **k: _Boom())
    with pytest.raises(OSError, match="disk full"):
        io.dump_text_atomic("data", dest)
    assert not dest.exists()
    # no leftover temp file in the destination directory
    assert list(dest.parent.glob(".r42topo-*.tmp")) == []


def test_effective_doc_hash_format_and_determinism():
    h = effective_doc_hash({"a": 1, "b": 2})
    assert h.startswith("sha256:") and len(h) == len("sha256:") + 64
    assert h == effective_doc_hash({"a": 1, "b": 2})


def test_effective_doc_hash_is_key_order_independent():
    # canonical hash sorts keys → insertion order must not matter
    assert effective_doc_hash({"a": 1, "b": 2}) == effective_doc_hash({"b": 2, "a": 1})


def test_effective_doc_hash_matches_backend_formula():
    # byte-compatible with range42-backend-api _effective_hash (ADR §9)
    doc = {"kind": "gamenet", "name": "x"}
    import hashlib
    expected = "sha256:" + hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert effective_doc_hash(doc) == expected
