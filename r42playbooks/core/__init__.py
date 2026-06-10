"""Pure core for r42playbooks: pydantic models, validation, IO, compiler.

This sub-package imports only pydantic, pyyaml, and the standard library.
It must remain free of CLI/TUI/web-framework imports so every consumer
(backend-api, CLI, TUI, deployment tooling) can import it cheaply.
"""
