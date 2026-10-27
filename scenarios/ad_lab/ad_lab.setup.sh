#!/bin/bash

##
## ad_lab.setup.sh - run the main playbook (Windows templates + domain controller + domain member)
##
## Same shape as kunai_lab.setup.sh (bundle-driven scenario wrappers).
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE
## to be exported - set by `range42-context use <codename> ad_lab`.
##
## Trailing "$@" propagates any extra args to ansible-playbook, e.g.
##   ./ad_lab.setup.sh -e FIREWALL_ARM_VMS=YES
## ad_lab has no feature flag (./manifest/feature_flags.yml : features: []).
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
