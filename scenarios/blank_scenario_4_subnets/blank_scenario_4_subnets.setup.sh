#!/bin/bash

##
## blank_scenario_4_subnets.setup.sh - run the main playbook (templates + 16 team VMs + 3 always-on admin VMs [+ optional admin tier])
##
## Same shape as kunai_lab.setup.sh (bundle-driven scenario wrappers).
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE
## to be exported - set by `range42-context use <codename> blank_scenario_4_subnets`.
##
## Trailing "$@" propagates any extra args to ansible-playbook.
## Typical use : feature flag overrides from the TUI, e.g.
##   ./blank_scenario_4_subnets.setup.sh -e INSTALL_WAZUH=YES
## See ./manifest/feature_flags.yml for the list of toggleable features.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
