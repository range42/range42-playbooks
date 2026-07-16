#!/bin/bash

##
## tier devkit : delete the dev tier VMs then redeploy this tier in isolation.
##

./stage_00-vm_bootstrap/r42_dev_deployer_ui_lab_group.devkit/dev_deployer_ui_lab.r42_dev_deployer_ui_lab_group.delete.sh

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "./_main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}"
