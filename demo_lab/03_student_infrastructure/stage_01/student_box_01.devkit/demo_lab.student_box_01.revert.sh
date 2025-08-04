#!/bin/bash

##
## ISSUE - 14
##

# vm_id 3001

proxmox_vm.list.to.jsons.sh | grep -i "student-box-01" | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh
proxmox_vm.list.to.jsons.sh | grep -i "student-box-01" | proxmox_vm.vm_id.start.to.jsons.sh
