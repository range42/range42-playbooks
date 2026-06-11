#!/bin/bash

##
## catalog_try.setup.sh - run the main playbook
##
## Same shape as demo_lab.setup.sh. catalog_try has no template stage, so this
## is functionally equivalent to catalog_try.setup_vms_only.sh ; both kept for
## interface compatibility with range42-context deploy / deploy-vms.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}"
