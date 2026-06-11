#!/bin/bash

##
## dev_deployer_ui_lab.setup.sh - run the main playbook (template + 3 VMs + Docker baseline)
##
## Same shape as misp_lab.setup.sh / catalog_try.setup.sh / demo_lab.setup.sh.
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE
## to be exported - set by `range42-context use <codename> dev_deployer_ui_lab`.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}"
