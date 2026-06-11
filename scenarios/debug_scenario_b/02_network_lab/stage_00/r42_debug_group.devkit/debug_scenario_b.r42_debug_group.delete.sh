#!/bin/bash

INFRASTRUCTURE_IP=(
    "192.168.148.250" # dsb-vm-01
)

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

proxmox_vm.list.to.jsons.sh | grep -i "dsb-vm" | jq -c | proxmox_vm.vm_id.stop.to.jsons.sh

sleep 2

proxmox_vm.list.to.jsons.sh | grep -i "dsb-vm" | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh
