#!/bin/bash 

VULN_BOX=(
    "192.168.142.170" # vuln-box-00
    "192.168.142.171" # vuln-box-01
    "192.168.142.172" # vuln-box-02
    "192.168.142.173" # vuln-box-03
    "192.168.142.174" # vuln-box-04
)

for ip in "${VULN_BOX[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

