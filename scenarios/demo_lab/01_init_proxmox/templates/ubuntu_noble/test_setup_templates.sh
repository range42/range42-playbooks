#!/bin/bash

##
## ISSUE - 3
##

ansible-playbook -i ../../..//inventory/off_cr_42.yml \
    -l "all" \
    "test_setup_templates.yml" --ask-vault-pass
