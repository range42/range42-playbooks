#!/bin/bash

##
## delete VMs only — keep templates
##

echo ":: stopping and deleting VMs (keeping templates)..."

proxmox_vm.list.to.jsons.sh | jq -c | grep -vi "template-vm" | grep -vi '"vm_template":1' | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | jq -c | grep -vi "template-vm" | grep -vi '"vm_template":1' | proxmox_vm.vm_id.delete.to.jsons.sh

INFRASTRUCTURE_IP=(
    "192.168.147.250" # dsa-vm-01
)

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

echo ""
echo ":: done — templates preserved"
echo ":: redeploy with: range42-context deploy"
echo ""
