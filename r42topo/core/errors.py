"""Framework-free exception hierarchy for the r42topo core.

Consumers (backend-api, CLI, r42deploy) translate these into their own surface
(HTTP envelopes, exit codes, dialog text). The core never raises framework
exceptions such as fastapi.HTTPException.
"""


class TopologyError(Exception):
    """Base class for all r42topo core errors."""


class ValidationError(TopologyError):
    """A document failed canonical-schema validation or the security deny-list."""


class CompileError(TopologyError):
    """An engine operation could not complete (e.g. VMID range exhausted)."""
