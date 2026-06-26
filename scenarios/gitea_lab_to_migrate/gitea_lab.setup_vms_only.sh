#!/bin/bash

##
## gitea_lab.setup_vms_only.sh - fast redeploy (skip template creation)
##
## Assumes template VMID 9232 is already present on Proxmox.
## Set environment first with: range42-context use <codename> gitea_lab
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "$SCRIPT_DIR/main_vms_only.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> gitea_lab}"
