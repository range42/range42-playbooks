#!/bin/bash

##
## ISSUE - 3
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "test_setup_templates.yml" --ask-vault-pass
