#!/bin/bash

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "r42.init-vm-00" \
	"../init_vm_00.yml" --vault-password-file /tmp/vault/vault_pass.txt
