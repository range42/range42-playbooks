#!/bin/bash

##
## ISSUE - 14
##

ansible-playbook -i ../../../inventory/off_cr_42.yml \
    -l "all" \
    "../vuln_box_00.yml" --vault-password-file /tmp/vault/vault_pass.txt
