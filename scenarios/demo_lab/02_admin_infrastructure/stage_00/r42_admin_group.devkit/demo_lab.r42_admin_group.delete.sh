#!/bin/bash

##
## ISSUE - 14
##

VULN_BOX=(

    "192.168.142.111" # testing-wazuh-client
    #
    "192.168.142.102" # admin-builder-api-devkit
    "192.168.142.101" # admin-builder-docker-registry
    "192.168.142.100" # admin-wazuh
    "192.168.142.120" # admin-web-api-kong
    "192.168.142.121" # admin-web-builder-api
    "192.168.142.122" # admin-web-emp
    "192.168.142.123" # admin-web-deployer-ui
    #
)

for ip in "${VULN_BOX[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

for line in $(proxmox_vm.list.to.jsons.sh | grep -i -E "(admin|testing-wazuh)" |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_vm.vm_id.stop.to.jsons.sh

    sleep 2
done

for line in $(proxmox_vm.list.to.jsons.sh | grep -i -E "(admin|testing-wazuh)" |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_vm.vm_id.delete.to.jsons.sh

    sleep 1
done
