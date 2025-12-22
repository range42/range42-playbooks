#!/bin/bash

ansible-playbook -i ../../../inventory/inventory_default.yml \
    -l "all" \
    "../vuln_box_01.yml" --vault-password-file /tmp/vault/vault_pass.txt
