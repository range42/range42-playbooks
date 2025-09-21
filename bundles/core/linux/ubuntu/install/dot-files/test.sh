#!/bin/bash 

# echo $TMP_RANGE42_ANSIBLE_INVENTORY_DIR ; exit 1 

ansible-playbook -i "$TMP_RANGE42_ANSIBLE_INVENTORY_DIR/off_cr_42.yml"  \
	-l "r42.vuln-box-00" \
    "./main.yml" \
    --vault-password-file /tmp/vault/vault_pass.txt
