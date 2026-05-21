#!/bin/bash

##
## 
##

VM_ID=$(devkit_manifest.find_vm_id.to.text.sh "$0" "init-vm-00") || exit 1
echo "{\"proxmox_node\":\"proxmox\",\"vm_id\":${VM_ID},\"vm_snapshot_description\":\"base\"}" | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
