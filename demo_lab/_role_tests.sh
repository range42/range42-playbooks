#!/bin/bash

# ADMIN_INFRASTRUCTURE_IP=(
#     "192.168.42.111" # testing-wazuh-client
#     #
#     "192.168.42.102" # admin-builder-api-devkit
#     "192.168.42.101" # admin-builder-docker-registry
#     "192.168.42.100" # admin-wazuh
#     "192.168.42.120" # admin-web-api-kong
#     "192.168.42.121" # admin-web-builder-api
#     "192.168.42.122" # admin-web-emp
# )

# for ip in "${ADMIN_INFRASTRUCTURE_IP[@]}"; do
#     echo ":: REMOVE SSH KEY FOR : $ip"
#     ssh-keygen -f "/home/grml/.ssh/known_hosts" -R "$ip"
# done

# proxmox_vm.list.to.jsons.sh | grep -i testing-wazuh-client | jq -c | proxmox_vm.vm_id.stop_force.to.jsons.sh | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
# proxmox_vm.list.to.jsons.sh | grep -vi template | grep -vi group | grep -iE "(admin-)|(testing-)" | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh

echo '{"proxmox_node":"px-testing","vm_id":1111 }' | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh
echo '{"proxmox_node":"px-testing","vm_id":1111 }' | proxmox_vm.vm_id.start.to.jsons.sh

# ANSIBLE_STDOUT_CALLBACK=skippy ansible-playbook -i ./inventory/off_cr_42.yml \
#      -l "all" \
#      "./demo_lab.testing.yml" --ask-vault-pass

sleep 10

# ANSIBLE_STDOUT_CALLBACK=skippy ansible-playbook -i ./inventory/off_cr_42.yml \
#     -l "r42.testing-wazuh-client" \
#     "./demo_lab.testing.yml" --vault-password-file /tmp/vault/vault_pass.txt

# ansible-playbook "./demo_lab.testing.yml" --syntax-check \
#     -l "r42.testing-wazuh-client" \
#     --vault-password-file /tmp/vault/vault_pass.txt

ansible-playbook -i ./inventory/off_cr_42.yml \
    -l "r42.testing-wazuh-client" \
    "./demo_lab.testing.yml" --vault-password-file /tmp/vault/vault_pass.txt

ssh r42.testing-wazuh-client -v
