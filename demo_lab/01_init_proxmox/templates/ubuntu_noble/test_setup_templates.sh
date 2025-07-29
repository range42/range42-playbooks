#!/bin/bash


ansible-playbook -i ./inventory/off_cr_42.yaml \
    -l "all" \
    "demo_lab.yaml" --ask-vault-pass
