"""r42playbooks — msfvenom-style range42 scenario generator.

Lists composable ``range42-catalog`` modules, lets a user compose a lab (flags,
a ``scenario.r42.yml`` spec, the CLI, or the TUI), and generates a real
``scenarios/<name>/`` directory in the existing demo_lab format — deployable
through the normal range42 flow with no changes elsewhere.

The pure core (``r42playbooks.core``) is framework-agnostic; the stable surface
(``r42playbooks.api``) is re-exported here so a downstream tool can drive
generation by import alone::

    import r42playbooks as r

    catalog = r.load_catalog("/path/to/range42-catalog")
    spec = r.load_spec("scenario.r42.yml")          # or r.ScenarioSpec.model_validate(...)
    if not r.validate_refs(spec, catalog):
        root = r.render_scenario(spec, catalog=catalog, dest="scenarios/")

Everything raises the ``r42playbooks.core.errors`` hierarchy — never a framework
type. CLI/TUI deps are optional extras (``pip install r42playbooks[cli]``, ``[tui]``).
"""

from r42playbooks.api import (
    Allocation,
    Catalog,
    ReservedIndex,
    ScenarioExistsError,
    ScenarioSpec,
    allocate,
    dump_spec_atomic,
    list_containers,
    list_roles,
    load_catalog,
    load_spec,
    render_scenario,
    validate_refs,
)
from r42playbooks.core.models import Topology

__all__ = [
    # generator surface (the stable import-only contract)
    "load_catalog",
    "list_roles",
    "list_containers",
    "validate_refs",
    "load_spec",
    "dump_spec_atomic",
    "allocate",
    "render_scenario",
    "ScenarioSpec",
    "Allocation",
    "Catalog",
    "ReservedIndex",
    "ScenarioExistsError",
    # legacy topology model (pre-pivot, kept for back-compat)
    "Topology",
    "__version__",
]
__version__ = "0.1.0"
