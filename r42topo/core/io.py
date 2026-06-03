"""Topology load/dump helpers — deterministic, atomic JSON IO.

``dump_topology`` writes sorted-key, stable JSON so re-compiling an unchanged
topology yields byte-identical output (clean diffs, reproducible builds).
Writes are atomic (temp file + os.replace) to avoid half-written artifacts.
"""

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError as _PydanticValidationError

from r42topo.core.errors import TopologyError
from r42topo.core.models import Topology


def load_topology(path: Path) -> Topology:
    """Load and validate a topology.json from *path*.

    :raises TopologyError: if the file is missing or not valid JSON.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TopologyError(f"cannot read topology file: {path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TopologyError(f"invalid JSON in topology file: {path}") from exc
    try:
        return Topology.model_validate(data)
    except _PydanticValidationError as exc:
        raise TopologyError(f"topology schema error in {path}: {exc}") from exc


def dumps_topology(topology: Topology) -> str:
    """Serialize a Topology to canonical, sorted, newline-terminated JSON."""
    payload = topology.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def dump_topology(topology: Topology, path: Path) -> Path:
    """Atomically write *topology* to *path* as canonical JSON. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = dumps_topology(topology)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".topology-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path
