#!/bin/bash

##
## ISSUE - 3
##

ansible-playbook -i ./inventory/off_cr_42.yaml \
    -l "all" \
    "demo_lab.yaml" --ask-vault-pass
