#!/bin/bash
echo '{"proxmox_node":"px-testing","vm_id":6023,"vm_snapshot_description":"base"}' | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
