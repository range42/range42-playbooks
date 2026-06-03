"""r42playbooks — range42 scenario authoring & topology compiler.

Pure, framework-agnostic core (``r42playbooks.core``) consumed by multiple frontends:
the range42-backend-api (FastAPI), this package's own Typer CLI / Textual TUI,
and the range42 deployment CLI/TUI. No frontend imports belong in ``core``.
"""

from r42playbooks.core.models import Topology

__all__ = ["Topology", "__version__"]
__version__ = "0.1.0"
