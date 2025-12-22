#!/bin/bash

##
## ISSUE - 14
##

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../web_emp.yml" --vault-password-file /tmp/vault/vault_pass.txt
