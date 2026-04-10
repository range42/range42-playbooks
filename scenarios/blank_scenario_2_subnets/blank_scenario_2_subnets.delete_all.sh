#!/bin/bash

proxmox_vm.list.to.jsons.sh | jq -c | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh

INFRASTRUCTURE_IP=(
    "192.168.143.200" # bs2-team-143-01
    "192.168.143.201" # bs2-team-143-02
    #
    "192.168.144.200" # bs2-team-144-01
    "192.168.144.201" # bs2-team-144-02
)

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done
