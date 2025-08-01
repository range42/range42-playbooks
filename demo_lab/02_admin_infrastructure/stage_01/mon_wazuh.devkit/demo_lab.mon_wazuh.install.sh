#!/bin/bash

##
## ISSUE - 14
##

ansible-playbook -i ../../../inventory/off_cr_42.yml \
    -l "all" \
    "../mon_wazuh.yml" --vault-password-file /tmp/vault/vault_pass.txt
