#!/bin/bash

##
## gitea_lab.delete_all.sh - delete VMs + templates declared in this scenario's manifest
##
## ⚠ WARNING ⚠
##   The medium ubuntu_noble template (VMID 9232) declared in gitea_lab's
##   manifest is also created and used by every other ubuntu_noble-consuming
##   scenario on the same Proxmox (demo_lab, blank_scenario_2_subnets,
##   blank_scenario_4_subnets, blank_scenario_6_subnets, _init_lab, kunai_lab,
##   misp_lab, dev_deployer_ui_lab, nextcloud_lab, mattermost_lab,
##   gitea_registry_lab). Running this script removes 9232 - those
##   scenarios will need to re-run their 01_init_proxmox/ to rebuild it before
##   re-deploy. Use gitea_lab.delete_vms_only.sh instead to keep the template
##   intact.
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
echo ":: done - VMs and template removed"
echo ":: redeploy from scratch with: range42-context deploy"
echo ""
