#!/bin/bash

##
## nextcloud_lab.setup.sh - run the main playbook (template + VM + Docker baseline)
##
## Same shape as catalog_try.setup.sh / demo_lab.setup.sh. Requires
## RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE to be
## exported - set by `range42-context use <codename> nextcloud_lab`.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}"
