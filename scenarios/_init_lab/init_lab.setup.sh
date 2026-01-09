#!/bin/bash

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./init_lab.yml" --vault-password-file /tmp/vault/vault_pass.txt
