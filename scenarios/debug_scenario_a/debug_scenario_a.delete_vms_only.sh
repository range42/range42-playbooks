#!/bin/bash

##
## delete VMs only — keep templates
##

echo ":: stopping and deleting VMs (keeping templates)..."

VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>&1)
if ! echo "$VM_LIST_JSON" | jq -e . >/dev/null 2>&1; then
    echo "ERROR: proxmox_vm.list.to.jsons.sh returned invalid JSON — aborting" >&2
    printf "output: %.200s\n" "$VM_LIST_JSON" >&2
    exit 1
fi
echo "$VM_LIST_JSON" | jq -c | grep -vi "template-vm" | grep -vi '"vm_template":1' | proxmox_vm.vm_id.stop_force.to.jsons.sh
echo "$VM_LIST_JSON" | jq -c | grep -vi "template-vm" | grep -vi '"vm_template":1' | proxmox_vm.vm_id.delete.to.jsons.sh

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
