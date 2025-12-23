#!/bin/bash

##
## ISSUE - 14
##

./stage_00/r42_vuln_box_group.devkit/demo_lab.vuln_box_01.delete.sh

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "./_main.yml" --vault-password-file /tmp/vault/vault_pass.txt
