#!/bin/bash

while IFS= read -r line; do
    ip="${line%% *}"
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done < <(devkit_manifest.find_ips_by_role.to.text.sh "$0" "team")

proxmox_vm.list.to.jsons.sh | grep -i "bs6-team" | jq -c | proxmox_vm.vm_id.stop.to.jsons.sh
sleep 2
proxmox_vm.list.to.jsons.sh | grep -i "bs6-team" | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh
