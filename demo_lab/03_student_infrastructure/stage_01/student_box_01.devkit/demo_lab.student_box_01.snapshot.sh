#!/bin/bash

##
## ISSUE - 14
##

proxmox_vm.list.to.jsons.sh | grep -i "student-box-01" | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
