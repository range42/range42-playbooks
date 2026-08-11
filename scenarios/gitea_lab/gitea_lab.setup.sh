#!/bin/bash

##
## gitea_lab.setup.sh - full provisioning (template + VM)
##
## Runs main.yml : 01_init_proxmox (idempotent) + VM clone + Docker baseline.
## Set environment first with: range42-context use <codename> gitea_lab
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "$SCRIPT_DIR/main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> gitea_lab}"
