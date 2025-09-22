#!/bin/bash

##
## ISSUE - 14
##

./stage_00/r42_vuln_box_group.devkit/demo_lab.vuln_box_01.delete.sh

ansible-playbook -i ../inventory/off_cr_42.yml \
    -l "all" \
    "./_main.yml" --vault-password-file /tmp/vault/vault_pass.txt
