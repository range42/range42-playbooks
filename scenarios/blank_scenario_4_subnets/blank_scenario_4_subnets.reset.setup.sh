#!/bin/bash

proxmox_vm.list.to.jsons.sh | jq -c | proxmox_vm.vm_id.stop_force.to.jsons.sh
proxmox_vm.list.to.jsons.sh | jq -c | proxmox_vm.vm_id.delete.to.jsons.sh

INFRASTRUCTURE_IP=(
    "192.168.143.210" # bs4-team-143-01
    "192.168.143.211" # bs4-team-143-02
    "192.168.143.212" # bs4-team-143-03
    "192.168.143.213" # bs4-team-143-04
    #
    "192.168.144.210" # bs4-team-144-01
    "192.168.144.211" # bs4-team-144-02
    "192.168.144.212" # bs4-team-144-03
    "192.168.144.213" # bs4-team-144-04
    #
    "192.168.145.210" # bs4-team-145-01
    "192.168.145.211" # bs4-team-145-02
    "192.168.145.212" # bs4-team-145-03
    "192.168.145.213" # bs4-team-145-04
    #
    "192.168.146.210" # bs4-team-146-01
    "192.168.146.211" # bs4-team-146-02
    "192.168.146.212" # bs4-team-146-03
    "192.168.146.213" # bs4-team-146-04
)

for ip in "${INFRASTRUCTURE_IP[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR}/inventory_default.yml" \
	-l "all" \
	"./main.yml" --vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?RANGE42_VAULT_PASSWORD_FILE is not set — run: range42-context use <codename> <scenario>}"
