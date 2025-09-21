#!/bin/bash

##
## ISSUE - 15
##

echo '{"proxmox_node":"px-testing","vm_id":1022,"vm_snapshot_description":"base"}' | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
