"""Range42 overlay operators (compose / expand_replication / …).

Pure dict transforms that mirror the TypeScript operators in
range42-deployer-ui/src/overlay/, kept in lock-step via the shared
schema/test-vectors/. These operate on canonical-schema documents
(``CatalogEntry`` dicts); divergence from the vectors is a failing build.

Ported from range42-backend-api (feature/gamenet-authoring-v1) as part of the
convergence that makes r42topo the single shared topology engine (issue #67).
"""

from r42topo.core.overlay.compose import compose
from r42topo.core.overlay.expand_replication import ExpandResult, expand_replication

__all__ = ["compose", "expand_replication", "ExpandResult"]
