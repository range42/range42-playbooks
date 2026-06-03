#!/bin/bash
##
## revert student-box-01 to its latest snapshot and restart it
##

VM_ID=$(devkit_manifest.find_vm_id.to.text.sh "$0" "student-box-01") || exit 1
echo "{\"proxmox_node\":\"px-testing\",\"vm_id\":${VM_ID} }" | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh
echo "{\"proxmox_node\":\"px-testing\",\"vm_id\":${VM_ID} }" | proxmox_vm.vm_id.start.to.jsons.sh
