#!/bin/bash

##
## kunai_lab.setup_vms_only.sh - run main_vms_only playbook
##
## Skips the 01_templates-bootstrap template stage. Use this when the medium
## template 9232 is already on the Proxmox (from a prior kunai_lab.setup.sh run
## or from another scenario that builds the same medium template).
## Equivalent to `range42-context deploy-vms`.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main_vms_only.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}"
