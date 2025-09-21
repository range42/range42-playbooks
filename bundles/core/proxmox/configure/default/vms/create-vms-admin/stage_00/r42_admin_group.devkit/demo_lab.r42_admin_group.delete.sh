#!/bin/bash

VULN_BOX=(

    # "192.168.42.111" # testing-wazuh-client
    #
    "192.168.42.102" # admin-builder-api-devkit
    "192.168.42.101" # admin-builder-docker-registry
    "192.168.42.100" # admin-wazuh
    "192.168.42.120" # admin-web-api-kong
    "192.168.42.121" # admin-web-builder-api
    "192.168.42.122" # admin-web-emp
    "192.168.42.123" # admin-web-deployer-ui
    #
)

for ip in "${VULN_BOX[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

proxmox_vm.list.to.jsons.sh | grep -i -E "(admin|testing-wazuh)" | proxmox_vm.vm_id.stop.to.jsons.sh
proxmox_vm.list.to.jsons.sh | grep -i -E "(admin|testing-wazuh)" | proxmox_vm.vm_id.delete.to.jsons.sh
