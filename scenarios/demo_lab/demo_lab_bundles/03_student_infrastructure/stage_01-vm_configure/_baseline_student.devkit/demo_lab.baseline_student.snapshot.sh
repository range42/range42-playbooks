#!/bin/bash

##
## VM filter is derived from manifest/scenario_vms.json (role=student).
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/../../../manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t VM_IDS < <(jq -r '.vms[] | select(.role == "student") | .vm_id' "$MANIFEST")
ID_REGEX=$(printf '|%s' "${VM_IDS[@]}" | sed 's/^|//')

VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh | grep '"vm_id":[0-9]')

for line in $(echo "$VM_LIST_JSON" | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)"); do
    printf "%s\n" "$line" | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
    sleep 2
done
