#!/bin/bash

##
## ISSUE - 14
##

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../_r42_admin.yml" --vault-password-file /tmp/vault/vault_pass.txt
