#!/bin/bash 

VULN_BOX=(
    "192.168.42.100" # r42.admin-wazuh
    "192.168.42.120" # r42.admin-web-api-kong
    "192.168.42.121" # r42.admin-web-builder-api
    "192.168.42.123" # r42.admin-web-deployer-ui
    "192.168.42.122" # r42.admin-web-emp
)

for ip in "${VULN_BOX[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

