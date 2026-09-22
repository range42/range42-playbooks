# vm.replace.sdn_vnet

Move one network card of a VM to another bridge.

**Destructive, and the verb says so.** There is no API to edit a card's bridge in place: the card is
deleted and recreated. Between the two the VM has one card less - so this is not the bundle to point at a
VM you reach *through* the card being moved.

**The MAC address is preserved.** It used to change, and this page used to call that wanted. It was not a choice, it was a limitation rationalised, and it cost two guests: cloud-init writes a netplan that carries `match: macaddress:`, so a new MAC makes `netplan apply` answer `Cannot find unique matching interface` and the guest loses its network. Nothing on the Proxmox side shows it - the api reports a healthy card, and only the guest knows it is cut. A DHCP reservation, an ipset or a firewall alias keyed on the MAC breaks the same way.

**Want a fresh MAC?** This bundle no longer gives you one, deliberately: preserving is the safe default and the dangerous case should be asked for out loud rather than inherited. Call the two underlying actions yourself, `network_delete_interfaces_vm` then `network_add_interfaces_vm` without `iface_macaddr`.

**A card whose MAC cannot be read is refused**, before anything is destroyed. Same sentence the model already makes: a card we cannot rebuild identically is a card we do not take apart. The MAC is read positionally from the first segment, which the api normalises to `<model>=<MAC>`, so an unreadable one means the card is not shaped as expected.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_VM_ID` | yes | `vm_id` | Proxmox VM id |
| `BUNDLE_VM_VMNET_ID` | yes | `vm_vmnet_id` | the slot to move, the N of `netN` |
| `BUNDLE_VM_IFACE_BRIDGE` | yes | `iface_bridge` | target bridge - a vnet or a legacy `vmbr` |
| `BUNDLE_VM_IFACE_MODEL` | no | `iface_model` | default: the model of the card being replaced |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

`iface_firewall` is **not** a parameter: it is read from the card and resent, which is the point of a
replace. For a fresh card, use `vm.attach.sdn_vnet`.

`iface_macaddr` is **not** a parameter either, for the same reason and with more at stake: it is read from the card and resent so the guest keeps the MAC its netplan matches on.

## What is preserved

**The slot.** The card comes back as the same `netN`, asked for explicitly. Left to a count-based
fallback, moving `net0` on a VM that also has `net1` would recreate `net1` **on top of** the existing
`net1` - a card move destroying a different card. That defect was real, and fixed in the devkit under
`#135`.

**The model.** Read from the card being replaced, so the caller does not repeat it.

**The firewall flag.** Read back and resent. This is the one place in the family where a two-branch task
is justified: the role emits that segment on `is defined`, and a bundle cannot leave a `vars:` key
undefined - so "resend it if it was there, omit it if it was not" needs two calls. The tested devkit does
the same with an `if`/`else`.

**The MAC.** Read back and resent, unconditionally - unlike the firewall flag it needs no second branch, because a card always carries one and one that does not is refused above. This is what keeps the guest's netplan matching its interface, and it is the difference between a card that moves and a guest that goes silent.

## Already on the target?

Nothing is destroyed. The move is skipped, reported, and the MAC is unchanged. Every destructive task
carries that same guard.

## Refused before anything is destroyed

A missing card, or a card whose model cannot be read, is refused **up front** - both are states from
which the recreate could not put things back. The failure message names the cards the VM really has.

## Related

- `vm.attach.sdn_vnet` - add a card without touching the existing ones.
- `vm.detach.sdn_vnet` - remove one.
- `vm.list.interfaces` - the read this bundle does internally, if you want it on its own.
- the devkit equivalent, whose behaviour this mirrors:
  `proxmox_network.vm_id.replace_interfaces_vm.to.jsons.sh`
