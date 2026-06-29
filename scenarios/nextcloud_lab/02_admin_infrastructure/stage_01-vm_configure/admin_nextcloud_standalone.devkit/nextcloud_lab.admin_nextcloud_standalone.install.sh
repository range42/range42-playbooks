#!/bin/bash

##
## devkit : re-run the admin-nextcloud install (thin wrapper to bundles/admin/software.install.nextcloud/main.yml).
## Pre-conditions : the admin-nextcloud-standalone VM must already exist (created via main scenario deploy
## or via setup.sh). This devkit script re-runs the install play independently, useful for
## re-applying after config changes.
##
## INSTALL_NEXTCLOUD=YES is forced here to bypass the import_playbook gate in admin-nextcloud.yml.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
    -l "all" \
    "../admin-nextcloud.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
    -e INSTALL_NEXTCLOUD=YES \
    "$@"
