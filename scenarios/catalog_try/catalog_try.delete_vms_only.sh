#!/bin/bash
set -euo pipefail

# Shared native deletion and exact guest-pin retirement, including verified
# already-absent recovery. Never remove a pin before independent absence proof.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/catalog_try_lifecycle.py"
