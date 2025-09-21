#!/bin/bash

##
## ISSUE - 14
##

ssh-keygen -f "/$HOME/.ssh/known_hosts" -R '192.168.42.160'

for line in $(proxmox_vm.list.to.jsons.sh | grep -i student |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_vm.vm_id.stop.to.jsons.sh

    sleep 2
done

for line in $(proxmox_vm.list.to.jsons.sh | grep -i student |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_vm.vm_id.delete.to.jsons.sh

    sleep 1
done
