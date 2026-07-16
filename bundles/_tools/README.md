# bundles/_tools - bundle parameter contracts

Each live bundle declares its caller-facing interface in a hand-authored
`bundle_parameters.src.yml` (the source of truth). `generate-bundle-params.py` validates it
against `bundle_parameters.schema.json` and emits `bundle_parameters.json` next to the bundle's
`main.yml`, for the backend/UI to consume.

## Usage

```bash
# regenerate every live bundle (+ coverage gate):
"$RANGE42_BUNDLE_DIR"/_tools/generate-bundle-params.py

# regenerate a single bundle:
"$RANGE42_BUNDLE_DIR"/_tools/generate-bundle-params.py generic/systems.configure.sudo
```

(The earlier `generate-bundle-params.sh` bash versions are superseded by the pure-Python tool and
kept only as history; the `.py` is authoritative.)

## Rules

- `bundle_parameters.src.yml` is hand-authored. `bundle_parameters.json` is generated - never edit it.
- A malformed source fails the run (nonzero exit); no JSON is emitted for it.
- The generator validates and cross-checks - it does NOT infer the interface. Params that are invisible
  to a static scan (role-only defaults, sub-playbook params, call-site flags, vault secrets) live in the
  source because only the maintainer knows they are public.
- `decom/` is excluded. `_examples/` holds reference annotations (a role-only bundle, a rename, a
  composite with a vault secret).
- The installed `yq` is python kislyuk (a jq wrapper), not mikefarah; the script detects the flavour.

See the plan: `______TODO_bundle-parameters-declaration.md` (workspace root).
