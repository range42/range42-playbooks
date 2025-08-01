#!/bin/bash

##
## ISSUE - 14
##

# proxmox_vm.list.to.jsons.sh |
#     grep -vi template |
#     grep -vi group |
#     grep -iE "(admin-)|(testing-)" |
#     jq -c |
#     proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh

# proxmox_vm.list.to.jsons.sh |
#     grep -vi template |
#     grep -vi group |
#     grep -iE "(admin-)|(testing-)" |
#     jq -c |
#     proxmox_vm.vm_id.start.to.jsons.sh

for line in $(proxmox_vm.list.to.jsons.sh | grep -i "vuln-box" |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh

    sleep 2
done

for line in $(proxmox_vm.list.to.jsons.sh | grep -i "vuln-box" |
    jq -c "."); do

    printf "%s\n" "$line" | proxmox_vm.vm_id.start.to.jsons.sh

    sleep 1
done
