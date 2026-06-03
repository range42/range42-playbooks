# Vendored canonical schema

`range42.schema.json` (+ `bundled.json`, refs-resolved) are **vendored copies** of the
canonical Range42 Scenario Schema v1, whose source of truth is:

> `range42-deployer-ui` → `schema/range42.schema.json` (and `schema/bundled.json`)

Do not hand-edit these here. To update:

1. Pull the latest from `range42-deployer-ui` `schema/`.
2. Regenerate the pydantic models (matches the deployer-ui `tools/generate-pydantic.sh`):

```bash
datamodel-codegen \
  --input r42topo/schema/bundled.json \
  --input-file-type jsonschema \
  --output r42topo/core/canonical.py \
  --output-model-type pydantic_v2.BaseModel \
  --use-annotated --field-constraints \
  --target-python-version 3.11 \
  --use-standard-collections --use-schema-description \
  --use-union-operator --use-double-quotes --disable-timestamp --reuse-model
```

A scenario/topology document validates as `CatalogEntry`; a project overlay as
`ProjectOverlay`. The shared parity test-vectors live under `tests/vectors/test-vectors/`
(also vendored from deployer-ui `schema/test-vectors/`) and are the acceptance suite for
the operator phases (compose / expand_replication / redaction).

TODO (convergence §7): replace this vendored copy with a git submodule of the deployer-ui
`schema/` or a CI drift-check, so it cannot silently diverge from the source of truth.
