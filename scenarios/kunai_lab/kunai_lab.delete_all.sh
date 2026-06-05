#!/bin/bash

##
## kunai_lab.delete_all.sh
##
## kunai_lab has no scenario-specific templates : the medium template
## (VMID 9232) is shared across scenarios that build the same medium image.
## So delete_all is functionally equivalent to delete_vms_only. Kept as an
## alias for interface compatibility with range42-context delete-everything.
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/kunai_lab.delete_vms_only.sh" "$@"
