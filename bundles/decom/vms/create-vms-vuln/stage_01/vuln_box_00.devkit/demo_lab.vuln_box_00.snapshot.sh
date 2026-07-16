#!/bin/bash

# proxmox_vm.list.to.jsons.sh | grep -i vuln-box-00 | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
echo '{"proxmox_node":"px-testing","vm_id":4000,"vm_snapshot_description":"base"}' | proxmox_snapshot_vm.vm_id.create_snapshot.to.jsons.sh
