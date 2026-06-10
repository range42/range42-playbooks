#!/bin/bash

##
## reset + full redeploy — delete everything then deploy from scratch
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ":: reset — deleting all VMs and templates..."
"$SCRIPT_DIR/demo_lab_network.delete_all.sh" || exit 1

echo ""
echo ":: redeploying from scratch..."
"$SCRIPT_DIR/demo_lab_network.setup.sh"
