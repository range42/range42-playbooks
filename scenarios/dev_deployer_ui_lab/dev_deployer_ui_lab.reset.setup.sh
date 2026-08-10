#!/bin/bash

##
## reset - delete this scenario's VMs (filter by vm_id from manifest) then re-deploy
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

echo ":: stopping and deleting scenario VMs (vm_ids: ${SCENARIO_VM_IDS[*]})..."

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

##
## Trailing "$@" propagates any extra args to ansible-playbook.
##

# Fail fast on a stale workspace. `RANGE42_BUNDLE_DIR` anchors every
# `import_playbook` in this scenario and is exported by `sourced_range42`. A
# workspace generated before that export exists resolves every bundle path to
# `/admin/...` and dies with an opaque "the playbook could not be found".
# Fix: re-run the workspace.credentials role (or `range42-context` re-init) to
# regenerate `sourced_range42`, then `range42-context use <codename> <scenario>`.
: "${RANGE42_BUNDLE_DIR:?RANGE42_BUNDLE_DIR is not set - your workspace predates the bundle-root export ; regenerate sourced_range42 and re-run: range42-context use <codename> dev_deployer_ui_lab}"
: "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR:?RANGE42_ANSIBLE_ROLES__INVENTORY_DIR is not set - run: range42-context use <codename> dev_deployer_ui_lab}"

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set - run: range42-context use <codename> <scenario>}" \
	"$@"
