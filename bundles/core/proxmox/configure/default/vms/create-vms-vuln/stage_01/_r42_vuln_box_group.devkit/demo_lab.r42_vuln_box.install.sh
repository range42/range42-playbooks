#!/bin/bash

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../_r42_vuln_box_group.yml" --vault-password-file /tmp/vault/vault_pass.txt
