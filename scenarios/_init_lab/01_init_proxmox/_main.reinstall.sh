#!/bin/bash

##
##
##

# ./stage_00/r42_admin_group.devkit/demo_lab.r42_admin_group.delete.sh

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "r42_init_vm_group,proxmox" \
	"./_main.yml" --vault-password-file /tmp/vault/vault_pass.txt
