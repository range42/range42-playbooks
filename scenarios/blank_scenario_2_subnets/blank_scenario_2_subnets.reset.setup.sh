#!/bin/bash

##
## reset — delete this scenario's VMs (filter by vm_id) then re-deploy
##

SCENARIO_VM_IDS=(5001 5002 5003 5004 5100 5101 5102 5103)
ID_REGEX=$(printf '|%s' "${SCENARIO_VM_IDS[@]}" | sed 's/^|//')

echo ":: stopping and deleting scenario VMs (vm_ids: ${SCENARIO_VM_IDS[*]})..."

proxmox_vm.list.to.jsons.sh | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | jq -c | grep -E "\"vm_id\":($ID_REGEX)([^0-9]|\$)" | proxmox_vm.vm_id.delete.to.jsons.sh

INFRASTRUCTURE_IP=(
    # team — vmbr143
    "192.168.143.200" # bs2-team-143-01
    "192.168.143.201" # bs2-team-143-02
    # team — vmbr144
    "192.168.144.200" # bs2-team-144-01
    "192.168.144.201" # bs2-team-144-02
    # admin — vmbr142
    "192.168.142.100" # bs2-admin-wazuh
    "192.168.142.120" # bs2-admin-deployer-api-gateway
    "192.168.142.121" # bs2-admin-deployer-api-backend
    "192.168.142.123" # bs2-admin-deployer-ui
)

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
