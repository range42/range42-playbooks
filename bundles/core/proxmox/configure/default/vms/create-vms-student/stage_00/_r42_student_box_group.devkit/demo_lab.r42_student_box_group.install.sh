#!/bin/bash

##
## ISSUE - 14
##

ansible-playbook -i "$TMP_RANGE42_ANSIBLE_INVENTORY_DIR/inventory_default.yml" \
    -l "all" \
    "../_r42_student_box_group.yml" --vault-password-file /tmp/vault/vault_pass.txt
