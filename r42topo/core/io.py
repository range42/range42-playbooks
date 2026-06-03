"""Deterministic, atomic JSON IO for canonical topology documents.

Canonical documents are plain dicts (validated against the generated
``canonical`` models). ``dumps_canonical`` produces sorted-key, stable,
newline-terminated JSON so re-emitting an unchanged document yields
byte-identical output (clean diffs, reproducible builds). ``dump_json_atomic``
writes via a temp file + ``os.replace`` to avoid half-written artifacts.

``effective_doc_hash`` is byte-compatible with range42-backend-api's
``_effective_hash`` (``json.dumps(sort_keys=True, separators=(",", ":"))``):
identical effective documents hash identically across the backend (managed
path) and r42deploy (infra-as-code path) — the per-context deploy-authority
guarantee of convergence ADR §9 (issue #67).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from r42topo.core.errors import TopologyError


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON document from *path*.

    :raises TopologyError: if the file is missing or not valid JSON.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TopologyError(f"cannot read document file: {path}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TopologyError(f"invalid JSON in document file: {path}") from exc


def dumps_canonical(doc: dict[str, Any]) -> str:
    """Serialize *doc* to canonical, sorted, newline-terminated JSON."""
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def dump_text_atomic(text: str, path: Path) -> Path:
    """Atomically write *text* to *path* (temp file + ``os.replace``).

    Avoids half-written artifacts on crash/interrupt — a torn ``hosts.yml`` or
    ``topology.json`` would silently mis-deploy. Returns the path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".r42topo-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def dump_json_atomic(doc: dict[str, Any], path: Path) -> Path:
    """Atomically write *doc* to *path* as canonical JSON. Returns the path."""
    return dump_text_atomic(dumps_canonical(doc), path)


def effective_doc_hash(doc: dict[str, Any]) -> str:
    """Return ``sha256:<hex>`` over the effective document.

    Byte-compatible with the backend's ``_effective_hash`` so the managed and
    infra-as-code deploy paths agree on a document's identity (ADR §9).
    """
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
