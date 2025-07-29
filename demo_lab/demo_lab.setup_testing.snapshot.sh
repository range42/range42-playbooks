#!/bin/bash

#
# TEST FILE  - issue #10
#

echo '{"proxmox_node":"px-testing","vm_id":1000,"vm_snapshot_description":"base"}' | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
echo '{"proxmox_node":"px-testing","vm_id":1111,"vm_snapshot_description":"base"}' | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
