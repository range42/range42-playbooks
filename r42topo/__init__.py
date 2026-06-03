"""r42topo — the range42 canonical topology engine.

Pure, framework-agnostic core (``r42topo.core``) consumed by multiple frontends:
range42-backend-api (FastAPI, managed path), this package's own Typer CLI, and
r42deploy (the infra-as-code CLI/TUI). No frontend imports belong in ``core``.

The engine speaks the canonical Range42 Scenario Schema v1 (``CatalogEntry`` /
``ProjectOverlay`` with a unified ``nodes[]`` array). See ``r42topo.api`` for the
adapter surface and ``docs/r42topo-convergence-plan.md`` (issue #67).
"""

from r42topo.core.canonical import CatalogEntry, ProjectOverlay

__all__ = ["CatalogEntry", "ProjectOverlay", "__version__"]
__version__ = "0.2.0"
