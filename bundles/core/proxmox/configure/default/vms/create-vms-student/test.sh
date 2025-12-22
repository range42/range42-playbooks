#!/bin/bash

# echo $TMP_RANGE42_ANSIBLE_INVENTORY_DIR ; exit 1

./stage_00/_r42_student_box_group.devkit/demo_lab.r42_student_box_group.delete.sh

echo "" 
echo " run init.yml" 
echo "" 

ansible-playbook -i "$TMP_RANGE42_ANSIBLE_INVENTORY_DIR/inventory_default.yml" \
    -l "all" \
    "./init.yml" --vault-password-file /tmp/vault/vault_pass.txt


echo "" 
echo " run main.yml" 
echo "" 

ansible-playbook -i "$TMP_RANGE42_ANSIBLE_INVENTORY_DIR/inventory_default.yml" \
    -l "all" \
    "./main.yml" --vault-password-file /tmp/vault/vault_pass.txt
