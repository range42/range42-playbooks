#!/bin/bash

##
##
##

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "r42_init_vm_group" \
	"../_r42_init_vm_group.yml" --vault-password-file /tmp/vault/vault_pass.txt
