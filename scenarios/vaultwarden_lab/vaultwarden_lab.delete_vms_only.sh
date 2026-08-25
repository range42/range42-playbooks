#!/bin/bash

##
## vaultwarden_lab.delete_vms_only.sh - destroy the vaultwarden_lab VM, keep templates
##
## VM IDs are read from the scenario manifest :
##   manifest/scenario_vms.json
##
## Lifted from catalog_try.delete_vms_only.sh, scoped to the vaultwarden_lab manifest
## (currently lists only admin-vaultwarden-standalone, VMID 1189, IP 192.168.142.189).
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

# extract VM IDs + IPs from the manifest (templates kept untouched)
mapfile -t SCENARIO_VM_IDS  < <(jq -r '.vms[].vm_id' "$MANIFEST")
mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip'   "$MANIFEST")
ID_REGEX=$(printf '|%s' "${SCENARIO_VM_IDS[@]}" | sed 's/^|//')

echo ":: stopping and deleting vaultwarden_lab VMs (keeping templates)..."
echo ":: vaultwarden_lab VMs: ${SCENARIO_VM_IDS[*]}"
echo ""

VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>&1 | grep '"vm_id":[0-9]')
if [ -z "$VM_LIST_JSON" ]; then
    echo "ERROR: proxmox_vm.list.to.jsons.sh returned no VM data (no vm_id lines) - aborting" >&2
    printf "output: %.200s\n" "$VM_LIST_JSON" >&2
    exit 1
fi
echo "$VM_LIST_JSON" | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.stop_force.to.jsons.sh
echo "$VM_LIST_JSON" | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.delete.to.jsons.sh

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

echo ""
echo ":: done - templates preserved"
echo ":: redeploy with: range42-context deploy-vms  (or ./vaultwarden_lab.setup_vms_only.sh)"
echo ""
