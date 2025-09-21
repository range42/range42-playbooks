#!/bin/bash

##
## ISSUE - 
##

ansible-playbook -i ../../../inventory/off_cr_42.yml \
    -l "all" \
    "../_r42_admin.yml" --vault-password-file /tmp/vault/vault_pass.txt
