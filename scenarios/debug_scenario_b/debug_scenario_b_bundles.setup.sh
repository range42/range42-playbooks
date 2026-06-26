#!/bin/bash

##
## debug_scenario_b_bundles.setup.sh - run the main playbook (template(s) + 1 lab VM [+ optional admin tier])
##
## Same shape as kunai_lab_bundles.setup.sh (bundle-driven scenario wrappers).
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE
## to be exported - set by `range42-context use <codename> debug_scenario_b`.
##
## Trailing "$@" propagates any extra args to ansible-playbook.
## Typical use : feature flag overrides from the TUI, e.g.
##   ./debug_scenario_b_bundles.setup.sh -e INSTALL_WAZUH=YES
## See ./manifest/feature_flags.yml for the list of toggleable features.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
