#!/bin/bash

##
## delete VMs only — keep templates
## faster redeploy: skip 01_init_proxmox (templates already exist)
##

echo ":: stopping and deleting VMs (keeping templates)..."

proxmox_vm.list.to.jsons.sh | jq -c | grep -vi "template-vm" | grep -vi '"vm_template":1' | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | jq -c | grep -vi "template-vm" | grep -vi '"vm_template":1' | proxmox_vm.vm_id.delete.to.jsons.sh

INFRASTRUCTURE_IP=(
    "192.168.142.111" # testing-wazuh-client
    #
    "192.168.142.102" # admin-builder-api-devkit
    "192.168.142.101" # admin-builder-docker-registry
    "192.168.142.100" # admin-wazuh
    "192.168.142.120" # admin-web-api-kong
    "192.168.142.121" # admin-web-builder-api
    "192.168.142.122" # admin-web-emp
    "192.168.142.123" # admin-web-deployer-ui
    #
    "192.168.143.160" # student-box-01
    #
    "192.168.144.170" # vuln-box-00
    "192.168.144.171" # vuln-box-01
    "192.168.144.172" # vuln-box-02
    "192.168.144.173" # vuln-box-03
    "192.168.144.174" # vuln-box-04
)

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

echo ""
echo ":: done — templates preserved"
echo ":: redeploy with: range42-context deploy"
echo ""
