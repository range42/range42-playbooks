#!/bin/bash

##
## ISSUE - 14
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "../web_emp.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
