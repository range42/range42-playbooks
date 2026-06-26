#!/bin/bash

##
## VM filter is derived from manifest/scenario_vms.json (group=admin),
## not from brittle vm_name regex.
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/../../../manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t VM_IDS < <(jq -r '.vms[] | select(.group == "admin") | .vm_id' "$MANIFEST")
mapfile -t VM_IPS < <(jq -r '.vms[] | select(.group == "admin") | .ip'    "$MANIFEST")
ID_REGEX=$(printf '|%s' "${VM_IDS[@]}" | sed 's/^|//')

for ip in "${VM_IPS[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh | grep '"vm_id":[0-9]')

echo "$VM_LIST_JSON" | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.stop.to.jsons.sh
echo "$VM_LIST_JSON" | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.delete.to.jsons.sh
