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
##   - blank_scenario_6_subnets.delete_vms_only.sh        — VMs only, keep templates
##   - blank_scenario_6_subnets.delete_all.sh (this)      — VMs + this scenario's templates
##

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$SCRIPT_DIR/manifest/scenario_vms.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: manifest not found: $MANIFEST" >&2
    exit 1
fi

mapfile -t SCENARIO_VM_IDS  < <(jq -r '.vms[].vm_id'        "$MANIFEST")
mapfile -t TEMPLATE_VM_IDS  < <(jq -r '.templates[].vm_id'  "$MANIFEST")
mapfile -t INFRASTRUCTURE_IP < <(jq -r '.vms[].ip'          "$MANIFEST")

ALL_IDS=("${SCENARIO_VM_IDS[@]}" "${TEMPLATE_VM_IDS[@]}")
ID_REGEX=$(printf '|%s' "${ALL_IDS[@]}" | sed 's/^|//')

echo ":: stopping and deleting VMs + templates"
echo ":: scenario VMs: ${SCENARIO_VM_IDS[*]}"
echo ":: templates   : ${TEMPLATE_VM_IDS[*]}"
echo ""

# the [WARNING] / jq parse error noise that may appear here comes from
# proxmox_vm.list.to.jsons.sh (Ansible warnings leaking to stdout) — non-fatal,
# the grep filter still catches the JSON lines properly. tracked separately.

proxmox_vm.list.to.jsons.sh | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.delete.to.jsons.sh

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

echo ""
echo ":: done — VMs and templates removed"
echo ":: redeploy from scratch with: range42-context deploy"
echo ""
