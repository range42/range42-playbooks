#!/bin/bash

##
## delete VMs only — scenario VMs (filter by vm_id), keep templates
##
## VM IDs and IPs are read from the scenario manifest:
##   manifest/scenario_vms.json
##
## Companions:
##   - blank_scenario_6_subnets.delete_vms_only.sh (this) — VMs only, keep templates
##   - blank_scenario_6_subnets.delete_all.sh             — VMs + this scenario's templates
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

echo ":: stopping and deleting scenario VMs (keeping templates)..."
echo ":: scenario VMs: ${SCENARIO_VM_IDS[*]}"
echo ""

proxmox_vm.list.to.jsons.sh | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.delete.to.jsons.sh

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

echo ""
echo ":: done — templates preserved"
echo ":: redeploy with: range42-context deploy"
echo ""
