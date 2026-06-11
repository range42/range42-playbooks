#!/bin/bash

##
## Trailing "$@" propagates any extra args to ansible-playbook.
## Typical use : feature flag overrides from the TUI, e.g.
##   demo_lab.setup.sh -e enable_wazuh=false -e enable_misp=true
## See ./manifest/feature_flags.yml for the list of toggleable features.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}" \
	"$@"
