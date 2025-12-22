#!/bin/bash

##
## ISSUE - 14
##

./stage_00/r42_admin_group.devkit/demo_lab.r42_admin_group.delete.sh

ansible-playbook -i ../inventory/inventory_default.yml \
    -l "all" \
    "./_main.yml" --vault-password-file /tmp/vault/vault_pass.txt
