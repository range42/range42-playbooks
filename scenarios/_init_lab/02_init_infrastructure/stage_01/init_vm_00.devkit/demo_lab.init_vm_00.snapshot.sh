#!/bin/bash

##
## 
##

echo '{"proxmox_node":"proxmox","vm_id":1000,"vm_snapshot_description":"base"}' | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
