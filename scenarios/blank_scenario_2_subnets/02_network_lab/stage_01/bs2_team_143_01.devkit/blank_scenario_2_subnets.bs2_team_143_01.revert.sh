#!/bin/bash

echo '{"proxmox_node":"px-testing","vm_id":5001 }' | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh
echo '{"proxmox_node":"px-testing","vm_id":5001 }' | proxmox_vm.vm_id.start.to.jsons.sh
