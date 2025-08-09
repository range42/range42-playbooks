#!/bin/bash

##
## ISSUE - 14
##

echo '{"proxmox_node":"px-testing","vm_id":4002,"vm_snapshot_description":"base"}' | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
