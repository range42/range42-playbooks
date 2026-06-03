"""Importable adapter — the canonical surface every frontend calls.

Consumed by range42-backend-api (FastAPI, managed path), r42topo's own CLI, and
r42deploy (CLI/TUI, infra-as-code path). Pure: operates on canonical-schema
documents (plain dicts validated against the generated ``canonical`` models),
returns plain models / dicts / paths, and raises the ``r42topo.core.errors``
hierarchy — never framework types. Each consumer maps these into its own
surface (HTTP envelopes, exit codes, dialogs).

This replaced the retired ``subnets/zones/boxes`` model + compiler during the
canonical convergence (issue #67): r42topo now speaks only the canonical
``CatalogEntry`` / ``ProjectOverlay`` (``nodes[]``) contract.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError as _PydanticValidationError

from r42topo.core.allocation import allocate_vmids
from r42topo.core.canonical import CatalogEntry, ProjectOverlay
from r42topo.core.errors import ValidationError
from r42topo.core.io import (
    dump_json_atomic,
    dump_text_atomic,
    dumps_canonical,
    effective_doc_hash,
    load_json,
)
from r42topo.core.inventory_writer import write_inventory
from r42topo.core.overlay import compose, expand_replication
from r42topo.core.preflight import (
    PreflightReport,
    check_topology_node_role,
    check_vmid_safety_for_topology,
)
from r42topo.core.security import document_freetext_violations

__all__ = [
    # documents
    "load_document",
    "validate_document",
    "validate_overlay",
    "assert_document_safe",
    "dumps_canonical",
    "dump_json_atomic",
    "dump_text_atomic",
    "effective_doc_hash",
    # operators
    "compose",
    "compose_effective",
    "expand_replication",
    "write_inventory",
    "allocate_vmids",
    # preflight
    "preflight_document",
    "PreflightReport",
    # models
    "CatalogEntry",
    "ProjectOverlay",
]


def load_document(path: Path) -> dict[str, Any]:
    """Load a canonical document (topology or overlay) from *path* as a dict."""
    return load_json(path)


def assert_document_safe(doc: dict[str, Any]) -> None:
    """Fail closed if *doc*'s free-text fields carry injection-bearing values.

    Scans ``defaults`` + each node's ``config`` / attachment ``vars`` against
    the deny-list (Jinja/SSTI, shell metacharacters, path traversal, argv
    flags). The controlled ``*_template`` fields are intentionally exempt.

    :raises ValidationError: listing every offending field path.
    """
    violations = document_freetext_violations(doc)
    if violations:
        raise ValidationError(
            "document contains forbidden values in: " + ", ".join(violations)
        )


def validate_document(doc: dict[str, Any]) -> CatalogEntry:
    """Validate *doc* as a canonical ``CatalogEntry`` (schema + security).

    Runs canonical-schema validation, then the fail-closed free-text deny-list
    scan. Both must pass.

    :raises ValidationError: on a schema failure or a deny-listed free-text value.
    """
    try:
        entry = CatalogEntry.model_validate(doc)
    except _PydanticValidationError as exc:
        raise ValidationError(f"invalid topology document: {exc}") from exc
    assert_document_safe(doc)
    return entry


def validate_overlay(doc: dict[str, Any]) -> ProjectOverlay:
    """Validate *doc* as a canonical ``ProjectOverlay`` (compose input).

    :raises ValidationError: if *doc* does not conform to the canonical schema.
    """
    try:
        return ProjectOverlay.model_validate(doc)
    except _PydanticValidationError as exc:
        raise ValidationError(f"invalid project overlay: {exc}") from exc


def compose_effective(
    base: dict[str, Any], overlay: dict[str, Any] | None
) -> tuple[dict[str, Any], str]:
    """Compose ``base`` + ``overlay`` into the effective doc and its hash.

    Returns ``(effective_doc, effective_doc_hash)``. The hash is byte-compatible
    with the backend so managed and IaC deploy paths agree (ADR §9). The
    effective document is deny-list scanned before returning, so overlay-injected
    values (``param_overrides``, ``nodes_added`` …) cannot slip through unchecked.

    :raises ValidationError: if a free-text field carries a deny-listed value.
    """
    eff = compose(base, overlay)
    assert_document_safe(eff)
    return eff, effective_doc_hash(eff)


def preflight_document(
    doc: dict[str, Any],
    *,
    team_count: int,
    host_overrides: list[list[int]] | None = None,
) -> PreflightReport:
    """Run the pure, synchronous topology preflight checks over *doc*.

    Covers VM/LXC node-role presence and topology-aware VMID safety. The impure
    checks (Proxmox/SDN/Docker/git reachability, asset resolution) live in the
    deploy runtime, not in the pure engine.
    """
    report = PreflightReport()
    report.checks.extend(check_topology_node_role(doc))
    report.checks.append(
        check_vmid_safety_for_topology(doc, team_count, host_overrides)
    )
    return report
