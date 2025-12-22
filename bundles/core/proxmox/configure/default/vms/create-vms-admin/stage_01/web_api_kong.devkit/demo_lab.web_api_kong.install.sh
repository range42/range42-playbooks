#!/bin/bash

##
## ISSUE - 
##

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../web_api_kong.yml" --vault-password-file /tmp/vault/vault_pass.txt
