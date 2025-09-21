#!/bin/bash

ansible-playbook -i ../../../inventory/off_cr_42.yml \
    -l "all" \
    "../vuln_box_04.yml" --vault-password-file /tmp/vault/vault_pass.txt
