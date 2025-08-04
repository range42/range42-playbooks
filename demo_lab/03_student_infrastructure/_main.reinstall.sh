#!/bin/bash

##
## ISSUE - 14
##

./stage_00/_r42_student_box_group.devkit/demo_lab.r42_student_box_group.delete.sh

ansible-playbook -i ../inventory/off_cr_42.yml \
    -l "all" \
    "./_main.yml" --vault-password-file /tmp/vault/vault_pass.txt
