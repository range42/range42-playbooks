#!/bin/bash

##
## dev_deployer_ui_lab.setup.sh - run the main playbook (templates + 3 dev VMs + 3 app bundles [+ optional admin tier])
##
## Same shape as kunai_lab.setup.sh / demo_lab.setup.sh (bundle-driven scenario wrappers).
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE
## to be exported - set by `range42-context use <codename> dev_deployer_ui_lab`.
##
## Trailing "$@" propagates any extra args to ansible-playbook.
## Typical use : feature flag overrides from the TUI, e.g.
##   ./dev_deployer_ui_lab.setup.sh -e INSTALL_WAZUH=YES
## See ./manifest/feature_flags.yml for the list of toggleable features.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
