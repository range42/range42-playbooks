#!/bin/bash 


proxmox_vm.list.to.jsons.sh | jq -c | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh


ADMIN_INFRASTRUCTURE_IP=(
    "192.168.42.111" # testing-wazuh-client
    #
    "192.168.42.102" # admin-builder-api-devkit
    "192.168.42.101" # admin-builder-docker-registry
    "192.168.42.100" # admin-wazuh
    "192.168.42.120" # admin-web-api-kong
    "192.168.42.121" # admin-web-builder-api
    "192.168.42.122" # admin-web-emp
    "192.168.42.123" # admin-web-deployer-ui
    #
    "192.168.42.160" # student-box-01
    #
    "192.168.42.170" # vuln-box-00
    "192.168.42.171" # vuln-box-01
    "192.168.42.172" # vuln-box-02
    "192.168.42.173" # vuln-box-03
    "192.168.42.174" # vuln-box-04
)

for ip in "${ADMIN_INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done
 

