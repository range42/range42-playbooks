#!/bin/bash



# for line in $(proxmox_vm.list.to.jsons.sh | grep -i student |
#     grep -iE "(admin-)|(testing-)" |
#     jq -c "."); do

#     printf "%s\n" "$line" | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh

#     sleep 2
# done

proxmox_vm.list.to.jsons.sh | grep -i student | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
