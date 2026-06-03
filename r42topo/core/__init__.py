"""Pure core for r42topo: canonical models, schema IO, overlay operators,
allocation/VMID safety, preflight, security, and inventory emit.

This sub-package imports only pydantic, pyyaml, and the standard library.
It must remain free of CLI/web-framework imports so every consumer
(backend-api, the Typer CLI, r42deploy) can import it cheaply.
"""
