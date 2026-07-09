#!/bin/bash

##
## devkit : re-run the admin-rocketchat install (thin wrapper to bundles/admin/software.install.rocketchat/main.yml).
## Pre-conditions : the admin-rocketchat-standalone VM must already exist (created via main scenario deploy
## or via setup.sh). This devkit script re-runs the install play independently, useful for
## re-applying after config changes.
##
## INSTALL_ROCKETCHAT=YES is forced here to bypass the import_playbook gate in admin-rocketchat.yml.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "../admin-rocketchat.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
    -e INSTALL_ROCKETCHAT=YES \
    "$@"
