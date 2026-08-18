#!/bin/bash

##
## debug_sdn_tests.setup.sh - run the main playbook (the SDN chain, through the bundles)
##
## Same shape as blank_scenario_2_subnets.setup.sh / kunai_lab.setup.sh.
## Requires RANGE42_ANSIBLE_ROLES__INVENTORY_DIR and RANGE42_VAULT_PASSWORD_FILE to be exported -
## set by `range42-context use <codename> debug_sdn_tests`.
##
## Trailing "$@" propagates any extra args to ansible-playbook. Typical use here is NOT a feature flag
## (this scenario has none) but a run parameter :
##   ./debug_sdn_tests.setup.sh -e sdn_test_vm_id=104
##   ./debug_sdn_tests.setup.sh -e sdn_test_zone=r42other -e sdn_test_subnet=192.168.198.0/24
##
## ⚠ WARNING ⚠
##   - the zone sdn_test_zone (default r42test) is DELETED at the start AND at the end of the run
##   - one network card of sdn_test_vm_id (default 102) is MOVED onto the test vnet and back. The card
##     is deleted and recreated, so ITS MAC CHANGES - twice. Never point this at a VM you reach
##     THROUGH that card.
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
