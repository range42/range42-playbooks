#!/bin/bash

##
## blank_scenario_2_subnets.setup_vms_only.sh - run main_vms_only.yml (skip template creation)
##
## Templates 9221 (small) + 9232 (medium, for admin-wazuh/misp) are assumed
## already present on the Proxmox. Used by `range42-context deploy-vms`.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main_vms_only.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
