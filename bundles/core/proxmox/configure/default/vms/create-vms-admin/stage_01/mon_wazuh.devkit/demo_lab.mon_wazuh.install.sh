#!/bin/bash

##
## ISSUE - 
##

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../mon_wazuh.yml" --vault-password-file /tmp/vault/vault_pass.txt
