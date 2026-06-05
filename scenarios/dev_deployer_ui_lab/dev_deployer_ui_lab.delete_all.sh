#!/bin/bash

##
## dev_deployer_ui_lab.delete_all.sh
##
## dev_deployer_ui_lab has no scenario-specific templates : the medium template
## (VMID 9232) is shared across scenarios (misp_lab, blank_scenario_2_subnets,
## demo_lab and any future medium-consuming lab). So delete_all is functionally
## equivalent to delete_vms_only. Kept as an alias for interface compatibility
## with range42-context delete-everything.
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/dev_deployer_ui_lab.delete_vms_only.sh" "$@"
