#!/bin/bash

echo '{"proxmox_node":"px-testing","vm_id":1000 }' | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh
echo '{"proxmox_node":"px-testing","vm_id":1000 }' | proxmox_vm.vm_id.start.to.jsons.sh
