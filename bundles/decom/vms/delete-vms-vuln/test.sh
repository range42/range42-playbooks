#!/bin/bash 

# echo $TMP_RANGE42_ANSIBLE_INVENTORY_DIR ; exit 1 

ansible-playbook -i "$TMP_RANGE42_ANSIBLE_INVENTORY_DIR/inventory_default.yml"  \
    "./main.yml" \
    --vault-password-file /tmp/vault/vault_pass.txt
	# -l "r42_vuln_box_group" \
