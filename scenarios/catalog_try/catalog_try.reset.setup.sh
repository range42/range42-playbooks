#!/bin/bash
set -euo pipefail

# Reset uses the same guarded DeleteVMs lifecycle before installing again.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/catalog_try.delete_vms_only.sh"
exec bash "$SCRIPT_DIR/catalog_try.setup.sh" "$@"
