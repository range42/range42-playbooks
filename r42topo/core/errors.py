"""Framework-free exception hierarchy for the r42topo core.

Consumers (backend-api, CLI, TUI) translate these into their own surface
(HTTP envelopes, exit codes, dialog text). The core never raises framework
exceptions such as fastapi.HTTPException.
"""


class TopologyError(Exception):
    """Base class for all r42topo core errors."""


class ValidationError(TopologyError):
    """A topology or template failed semantic validation (beyond schema)."""


class CatalogNotFoundError(TopologyError):
    """A referenced catalog template id/version could not be resolved."""


class CompileError(TopologyError):
    """Compilation failed (reservation conflict, segmentation invariant, etc.)."""
