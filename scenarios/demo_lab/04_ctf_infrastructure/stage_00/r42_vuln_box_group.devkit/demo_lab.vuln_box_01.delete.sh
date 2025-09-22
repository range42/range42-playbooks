#!/bin/bash

##
## ISSUE - 14
##

VULN_BOX=(

    #
    "192.168.42.170" # vuln-box-00
    "192.168.42.171" # vuln-box-01
    "192.168.42.172" # vuln-box-02
    "192.168.42.173" # vuln-box-03
    "192.168.42.174" # vuln-box-04
)

for ip in "${VULN_BOX[@]}"; do
    echo ":: REMOVE SSH KEY FOR : $ip"
    ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$ip"
done

for line in $(proxmox_vm.list.to.jsons.sh | grep -i "vuln-box" |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_vm.vm_id.stop.to.jsons.sh

    sleep 2
done

for line in $(proxmox_vm.list.to.jsons.sh | grep -i "vuln-box" |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_vm.vm_id.delete.to.jsons.sh

    sleep 1
done
