#!/bin/bash

##
## catalog_try.delete_all.sh
##
## catalog_try has no scenario-specific templates (it reuses the template from
## another scenario's setup, e.g. demo_lab). So delete_all is functionally
## equivalent to delete_vms_only here. Kept as an alias for interface
## compatibility with range42-context delete-everything.
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/catalog_try.delete_vms_only.sh" "$@"
