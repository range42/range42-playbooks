#!/bin/bash

##
## ISSUE - 14
##

#
# proxmox_vm.list.to.jsons.sh |
#     grep -vi template |
#     grep -vi group |
#     grep -iE "(admin-)|(testing-)" |
#     jq -c "." |
#     proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh

for line in $(proxmox_vm.list.to.jsons.sh | grep -i "vuln-box" |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh

    sleep 2
done
