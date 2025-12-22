#!/bin/bash

##
## ISSUE - 
##

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../web_deployer_ui.yml" --vault-password-file /tmp/vault/vault_pass.txt
