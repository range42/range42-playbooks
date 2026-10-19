#!/bin/bash
set -euo pipefail

##
## delete VMs only - catalog_try VM (single VM, filter by vm_id), keep templates
##
## VM IDs are read from the scenario manifest:
##   manifest/scenario_vms.json
##
## Lifted from demo_lab.delete_vms_only.sh, scoped to the catalog_try manifest
## (which currently lists only catalog-try-vm-docker, VMID 1250, IP 192.168.142.250).
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

echo ":: stopping and deleting catalog_try VMs (keeping templates)..."
echo ":: catalog_try VMs: ${SCENARIO_VM_IDS[*]}"
echo ""

# Preserve the native command's exit status: an empty successful inventory is
# expected on the participant's first run. API/authentication failures still stop.
if ! VM_LIST_JSON=$(proxmox_vm.list.to.jsons.sh); then
    echo "ERROR: native VM inventory query failed - no deletion attempted" >&2
    exit 1
fi
if [[ -z "${VM_LIST_JSON//[[:space:]]/}" ]]; then
    echo ":: no VMs exist; nothing to delete"
    exit 0
fi
if ! printf '%s\n' "$VM_LIST_JSON" | jq -e -s 'all(.[]; type == "object" and (.vm_id | type == "number"))' >/dev/null; then
    echo "ERROR: native VM inventory is invalid - no deletion attempted" >&2
    exit 1
fi
SELECTED=$(printf '%s\n' "$VM_LIST_JSON" | jq -c --argjson ids "$(jq '[.vms[].vm_id]' "$MANIFEST")" 'select(.vm_id as $id | $ids | index($id))')
if [[ -z "$SELECTED" ]]; then
    echo ":: catalog_try VMs are already absent; templates preserved"
    exit 0
fi
printf '%s\n' "$SELECTED" | proxmox_vm.vm_id.stop_force.to.jsons.sh
printf '%s\n' "$SELECTED" | proxmox_vm.vm_id.delete.to.jsons.sh

# Native API attempts keep their verified pins in the registered workspace.
# Remove only this deleted guest's pin; another context's SSH home stays intact.
KNOWN_HOSTS="$HOME/.ssh/known_hosts"
if [[ -n "${RANGE42_SOURCE_CONTEXT_DIR:-}" ]]; then
    KNOWN_HOSTS="${RANGE42_SOURCE_CONTEXT_DIR%/}/ssh_keys/known_hosts"
fi
if [[ -f "$KNOWN_HOSTS" ]]; then
    for ip in "${INFRASTRUCTURE_IP[@]}"; do
        echo ":: REMOVE SSH KEY FOR : $ip"
        ssh-keygen -f "$KNOWN_HOSTS" -R "$ip"
    done
fi

echo ""
echo ":: done - templates preserved"
echo ":: redeploy with: range42-context catalog-try <path>  (or range42-context deploy-vms)"
echo ""
