#!/bin/bash

ansible-playbook -i ../../../inventory/off_cr_42.yml \
    -l "all" \
    "../web_emp.yml" --vault-password-file /tmp/vault/vault_pass.txt
