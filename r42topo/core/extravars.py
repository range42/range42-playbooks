"""Build the extravars dict the ``_universal`` scenario consumes.

The backend calls ``run_playbook_core(scenarios/_universal/main.yml, inventory,
extravars=...)``; ``_universal`` asserts ``r42_topology_path`` is set and points
at a real file. This builder emits ONLY the allow-listed ``r42_*`` keys — no
``ansible_*`` or arbitrary keys can leak into the playbook's variable space.
Identifier values are deny-list checked (no injection into templated vars).
"""

from r42topo.core import constants as C
from r42topo.core.compiler import CompileResult
from r42topo.core.errors import ValidationError

# the exact contract keys _universal/main.yml expects
_ALLOWED_KEYS = (
    "r42_topology_path", "r42_inventory_dir", "r42_deployment_id",
    "r42_attempt_id", "r42_scope", "r42_team_id",
)


def _safe_id(name: str, value: str) -> str:
    if C.violates_denylist(value):
        raise ValidationError(f"{name} contains a forbidden character or pattern")
    return value


def resolve_universal_extravars(
    result: CompileResult,
    *,
    deployment_id: str,
    attempt_id: str,
    scope: str,
    team_id: str | None = None,
) -> dict:
    """Return the typed, allow-listed extravars for the ``_universal`` playbook."""
    extravars = {
        "r42_topology_path": str(result.topology_path),
        "r42_inventory_dir": str(result.workspace / "inventory"),
        "r42_deployment_id": _safe_id("deployment_id", deployment_id),
        "r42_attempt_id": _safe_id("attempt_id", attempt_id),
        "r42_scope": _safe_id("scope", scope),
        "r42_team_id": _safe_id("team_id", team_id) if team_id else "",
    }
    # defensive: guarantee no key escaped the allow-list (explicit, not assert —
    # assert is stripped under `python -O`)
    if set(extravars) != set(_ALLOWED_KEYS):
        raise ValidationError(
            f"extravars key mismatch: {set(extravars) ^ set(_ALLOWED_KEYS)}"
        )
    return extravars
