#!/bin/bash
##
## snapshot student-box-00 as "base"
##

VM_ID=$(devkit_manifest.find_vm_id.to.text.sh "$0" "student-box-00") || exit 1
echo "{\"proxmox_node\":\"px-testing\",\"vm_id\":${VM_ID},\"vm_snapshot_description\":\"base\"}" | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
