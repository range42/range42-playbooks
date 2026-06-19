#!/bin/bash

##
## debug_scenario_b_bundles.setup_vms_only.sh - run main_vms_only.yml (skip template creation)
##
## Same shape as kunai_lab_bundles.setup_vms_only.sh. Templates 9903 / 9232 are
## assumed already present on the Proxmox (built by a prior setup.sh or by
## another scenario). Used by `range42-context deploy-vms`.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main_vms_only.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
