#!/bin/bash
VM_ID=$(devkit_manifest.find_vm_id.to.text.sh "$0" "bs6-team-147-02") || exit 1
echo "{\"proxmox_node\":\"px-testing\",\"vm_id\":${VM_ID} }" | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh
echo "{\"proxmox_node\":\"px-testing\",\"vm_id\":${VM_ID} }" | proxmox_vm.vm_id.start.to.jsons.sh
