#!/bin/bash

##
## ISSUE - 3
##

ansible-playbook -i ../../..//inventory/inventory_default.yml \
    -l "all" \
    "test_setup_templates.yml" --ask-vault-pass
