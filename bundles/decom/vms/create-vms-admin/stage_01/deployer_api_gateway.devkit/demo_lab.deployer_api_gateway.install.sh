#!/bin/bash

##
##

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../deployer_api_gateway.yml" --vault-password-file /tmp/vault/vault_pass.txt
