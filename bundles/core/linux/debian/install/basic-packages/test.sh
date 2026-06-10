#!/bin/bash 

# echo $TMP_RANGE42_ANSIBLE_INVENTORY_DIR ; exit 1 

ansible-playbook -i "$TMP_RANGE42_ANSIBLE_INVENTORY_DIR/inventory_default.yml"  \
	-l "r42.debian-jump-00" \
    "./main.yml" \
    --vault-password-file /tmp/vault/vault_pass.txt
