#!/bin/bash

##
## deploy VMs only — skip template download and creation
## faster redeploy when templates already exist on proxmox
##
## Trailing "$@" propagates any extra args to ansible-playbook.
## Typical use : feature flag overrides from the TUI, e.g.
##   demo_lab.setup_vms_only.sh -e enable_wazuh=false
## See ./manifest/feature_flags.yml for the list of toggleable features.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main_vms_only.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}" \
	"$@"
