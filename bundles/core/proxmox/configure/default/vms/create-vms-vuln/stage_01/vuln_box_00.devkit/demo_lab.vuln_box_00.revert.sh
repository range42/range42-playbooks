#!/bin/bash

proxmox_vm.list.to.jsons.sh | grep -i vuln-box-00 | proxmox_snapshot_vm.vm_id.revert_snapshot.to.jsons.sh
proxmox_vm.list.to.jsons.sh | grep -i vuln-box-00 | proxmox_vm.vm_id.start.to.jsons.sh
