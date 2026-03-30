#!/bin/bash

##
## ISSUE - 14
##

./stage_00/r42_vuln_box_group.devkit/demo_lab.vuln_box_01.delete.sh

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "./_main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
