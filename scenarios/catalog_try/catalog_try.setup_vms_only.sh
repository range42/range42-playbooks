#!/bin/bash

##
## catalog_try.setup_vms_only.sh - run main_vms_only playbook
##
## catalog_try has no template stage to skip (template is assumed present from
## another scenario's setup). This script is functionally equivalent to
## catalog_try.setup.sh, kept for interface compatibility with
## `range42-context deploy-vms`.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main_vms_only.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}"
