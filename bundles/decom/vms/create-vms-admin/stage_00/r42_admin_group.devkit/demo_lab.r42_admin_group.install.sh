#!/bin/bash



ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../_r42_admin_group.yml" --vault-password-file /tmp/vault/vault_pass.txt
