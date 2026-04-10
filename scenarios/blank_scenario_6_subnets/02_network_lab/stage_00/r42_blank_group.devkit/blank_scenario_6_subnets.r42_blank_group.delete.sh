#!/bin/bash

INFRASTRUCTURE_IP=(
    "192.168.143.220" # bs6-team-143-01
    "192.168.143.221" # bs6-team-143-02
    "192.168.143.222" # bs6-team-143-03
    "192.168.143.223" # bs6-team-143-04
    #
    "192.168.144.220" # bs6-team-144-01
    "192.168.144.221" # bs6-team-144-02
    "192.168.144.222" # bs6-team-144-03
    "192.168.144.223" # bs6-team-144-04
    #
    "192.168.145.220" # bs6-team-145-01
    "192.168.145.221" # bs6-team-145-02
    "192.168.145.222" # bs6-team-145-03
    "192.168.145.223" # bs6-team-145-04
    #
    "192.168.146.220" # bs6-team-146-01
    "192.168.146.221" # bs6-team-146-02
    "192.168.146.222" # bs6-team-146-03
    "192.168.146.223" # bs6-team-146-04
    #
    "192.168.147.220" # bs6-team-147-01
    "192.168.147.221" # bs6-team-147-02
    "192.168.147.222" # bs6-team-147-03
    "192.168.147.223" # bs6-team-147-04
    #
    "192.168.148.220" # bs6-team-148-01
    "192.168.148.221" # bs6-team-148-02
    "192.168.148.222" # bs6-team-148-03
    "192.168.148.223" # bs6-team-148-04
    #
)

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

proxmox_vm.list.to.jsons.sh | grep -i "bs6-team" | jq -c | proxmox_vm.vm_id.stop.to.jsons.sh
sleep 2
proxmox_vm.list.to.jsons.sh | grep -i "bs6-team" | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh
