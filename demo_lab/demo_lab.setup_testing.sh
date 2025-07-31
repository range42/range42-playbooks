#!/bin/bash


#
# TEST FILE  - issue #10
#

####
#### DEMO_LAB EARLY DRAFT SCRIPT.
####

# ssh-add /home/grml/.ssh/cr42-dev-key
# ssh-add /home/grml/.ssh/off_green_edge
# ssh-add /home/grml/.ssh/off_green_edge_proxmox_forum

proxmox_vm.list.to.jsons.sh | grep -vi template | jq -c | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | grep -vi template | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh

ADMIN_INFRASTRUCTURE_IP=(
    "192.168.42.111" # testing-wazuh-client
    #
    "192.168.42.102" # admin-builder-api-devkit
    "192.168.42.101" # admin-builder-docker-registry
    "192.168.42.100" # admin-wazuh
    "192.168.42.120" # admin-web-api-kong
    "192.168.42.121" # admin-web-builder-api
    "192.168.42.122" # admin-web-emp
)

for ip in "${ADMIN_INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "/home/grml/.ssh/known_hosts" -R "$ip"
done

proxmox_vm.list.to.jsons.sh | grep -vi template | grep -vi group | grep -iE "(admin-)|(testing-)" | jq -c | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | grep -vi template | grep -vi group | grep -iE "(admin-)|(testing-)" | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh

ANSIBLE_STDOUT_CALLBACK=skippy ansible-playbook -i ./inventory/off_cr_42.yml \
    -l "all" \
    "./demo_lab.testing.yml" --vault-password-file /tmp/vault/vault_pass.txt

# ANSIBLE_STDOUT_CALLBACK=skippy ansible-playbook -i ./inventory/off_cr_42.yml \
#     -l "all" \
    


