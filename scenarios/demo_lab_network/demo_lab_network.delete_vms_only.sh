#!/bin/bash

##
## delete VMs only — keep templates
## faster redeploy: skip 01_init_proxmox (templates already exist)
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t SCENARIO_VM_IDS  < <(jq -r '.vms[].vm_id' "$MANIFEST")
mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip'   "$MANIFEST")

ID_REGEX=$(printf '|%s' "${SCENARIO_VM_IDS[@]}" | sed 's/^|//')

echo ":: stopping and deleting VMs (keeping templates)..."
echo ":: scenario VMs: ${SCENARIO_VM_IDS[*]}"
echo ""

VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>&1)
if ! echo "$VM_LIST_JSON" | jq -e . >/dev/null 2>&1; then
    echo "ERROR: proxmox_vm.list.to.jsons.sh returned invalid JSON — aborting" >&2
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
echo ":: done — templates preserved"
echo ":: redeploy with: range42-context deploy"
echo ""
