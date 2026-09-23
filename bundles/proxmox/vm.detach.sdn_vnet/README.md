# vm.detach.sdn_vnet

Remove one network card from a VM.

**Subject `vm`, not `sdn_network`**: it removes a card on a legacy `vmbr` as readily as one on a vnet.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_VM_ID` | yes | `vm_id` | Proxmox VM id |
| `BUNDLE_VM_VMNET_ID` | yes | `vm_vmnet_id` | the card slot, the N of `netN` |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

**No bridge parameter, and that is not an omission**: the API addresses a card by its **slot**, not by
what it is attached to.

Read `BUNDLE_VM_VMNET_ID` from `vm.list.interfaces` rather than assuming it - a VM's cards are not
necessarily numbered without holes.

## Why it reads before deleting

Deleting a slot the VM does not have is a silent no-op on some Proxmox versions and an error on others.
Reading first turns both into one clear refusal that names the cards the VM really has.

## This is what frees a vnet

Proxmox **refuses to delete a vnet that still carries a VM card**. A delete that goes straight to
`sdn_network.delete.sdn_vnet` without detaching first fails, and the failure blames the vnet rather than
the card. Detach first - or move the card elsewhere with `vm.replace.sdn_vnet`.

## Related

- `vm.replace.sdn_vnet` - move the card instead of removing it; preserves model, firewall flag and slot.
- `vm.attach.sdn_vnet` - add a card.
- `vm.list.interfaces` - which slots exist, and on which bridge.
- the devkit equivalent: `proxmox_network.vm_id.delete_interfaces_vm.to.jsons.sh`
