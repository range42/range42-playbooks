#!/bin/bash

##
## ISSUE - 14
##

# ansible-playbook -i ../../../inventory/inventory_default.yml \
#     -l "r42.student-box-01" \
#     "../_r42_student_box_group.yml" --vault-password-file /tmp/vault/vault_pass.txt

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../student_box_01.yml" --vault-password-file /tmp/vault/vault_pass.txt
