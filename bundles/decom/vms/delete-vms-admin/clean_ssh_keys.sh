#!/bin/bash 

VULN_BOX=(
    "192.168.142.100" # r42.admin-wazuh
    "192.168.142.120" # r42.admin-deployer-api-gateway
    "192.168.142.121" # r42.admin-deployer-api-backend
    "192.168.142.123" # r42.admin-deployer-ui
)

for ip in "${VULN_BOX[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

