#!/bin/bash 


VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>&1)
if ! echo "$VM_LIST_JSON" | jq -e . >/dev/null 2>&1; then
    echo "ERROR: proxmox_vm.list.to.jsons.sh returned invalid JSON — aborting" >&2
    printf "output: %.200s\n" "$VM_LIST_JSON" >&2
    exit 1
fi
echo "$VM_LIST_JSON" | jq -c | proxmox_vm.vm_id.stop_force.to.jsons.sh
echo "$VM_LIST_JSON" | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh


VM_INFRASTRUCTURE_IP=(
    "192.168.142.120" # init_vm_00
    "192.168.142.121" # init_vm_01
    "192.168.142.122" # init_vm_02
    "192.168.142.123" # init_vm_03
    "192.168.142.124" # init_vm_03
    "192.168.142.125" # init_vm_03
    # 
)

for ip in "${VM_INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done
 

