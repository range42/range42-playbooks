#!/bin/bash

##
## ISSUE - 14
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "../web_emp.yml" --vault-password-file /tmp/vault/vault_pass.txt
