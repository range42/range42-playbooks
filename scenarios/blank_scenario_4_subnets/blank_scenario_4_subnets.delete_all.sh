#!/bin/bash

##
## delete all — VMs + ubuntu_noble templates of THIS scenario
##
## VM IDs and IPs are read from the scenario manifest:
##   manifest/scenario_vms.json
##
## ⚠ WARNING ⚠
##   Templates (9xxx) are deleted by this script. They may be shared with other
##   scenarios deployed on the same Proxmox (every blank_scenario_*_subnets / demo_lab
##   creates the same template IDs). Run this only when you're sure no other
##   scenario relies on them, or run delete_vms_only.sh instead to keep templates.
##
## Companions:
##   - blank_scenario_4_subnets.delete_vms_only.sh        — VMs only, keep templates
##   - blank_scenario_4_subnets.delete_all.sh (this)      — VMs + this scenario's templates
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

# extract VM IDs + template IDs + IPs from the manifest
mapfile -t SCENARIO_VM_IDS  < <(jq -r '.vms[].vm_id'        "$MANIFEST")
mapfile -t TEMPLATE_VM_IDS  < <(jq -r '.templates[].vm_id'  "$MANIFEST")
mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip'          "$MANIFEST")

ALL_IDS=("${SCENARIO_VM_IDS[@]}" "${TEMPLATE_VM_IDS[@]}")
ID_REGEX=$(printf '|%s' "${ALL_IDS[@]}" | sed 's/^|//')

echo ":: stopping and deleting VMs + templates"
echo ":: scenario VMs: ${SCENARIO_VM_IDS[*]}"
echo ":: templates   : ${TEMPLATE_VM_IDS[*]}"
echo ""

VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh 2>&1 | grep '"vm_id":[0-9]')
if [ -z "$VM_LIST_JSON" ]; then
    echo "ERROR: proxmox_vm.list.to.jsons.sh returned no VM data (no vm_id lines) — aborting" >&2
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
echo ":: done — VMs and templates removed"
echo ":: redeploy from scratch with: range42-context deploy"
echo ""
