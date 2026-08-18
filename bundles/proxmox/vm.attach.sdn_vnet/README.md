# vm.attach.sdn_vnet

Add a network card to a VM. **Additive** - every existing card is left alone.

To *move* a card, use `vm.replace.sdn_vnet`, which deletes and recreates it (and changes its MAC).

**Subject `vm`, not `sdn_network`**: `BUNDLE_VM_IFACE_BRIDGE` takes a vnet name (`net142`) exactly as
readily as a legacy bridge (`vmbr0`). The bundle does not check which, and does not care.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_VM_ID` | yes | `vm_id` | Proxmox VM id |
| `BUNDLE_VM_IFACE_BRIDGE` | yes | `iface_bridge` | vnet name or legacy bridge |
| `BUNDLE_VM_IFACE_MODEL` | no | `iface_model` | NIC model, default `virtio` |
| `BUNDLE_VM_VMNET_ID` | **yes** | `vm_vmnet_id` | the interface slot, the N of `netN` |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

## The interface id is explicit, and the bundle never guesses it

`BUNDLE_VM_VMNET_ID` is **required**. Deriving it - from the card count, or from the lowest free slot -
is wrong for a reason that has nothing to do with the arithmetic being right: **the caller's numbering
may carry meaning**, for instance a `netN` chosen to match the subnet the card belongs to. A bundle that
picks a "free" id would silently break that convention. So the caller states the slot, always.

## What is still checked, and why that is not guessing

The cards are read and the requested slot is **refused if it is already taken**. `POST config` with
`net5` *replaces* `net5` whatever it held - a destructive silent success, and looking first is the only
way to catch it. The failure message names the bridge that card was on, and the slots in use.

## Why `iface_firewall` and `iface_link_down` are not parameters

The role emits their segment on `if iface_firewall is defined` - the right idiom for building a string.
But a bundle **cannot leave a `vars:` key undefined**, and bridging with `| default(omit)` makes the var
arrive DEFINED-but-placeholder, so the role emits `firewall=0` - silently disabling the firewall of a
card whose caller said nothing. Tested:

```
pas de bridge        -> defini=False  ->  segment omis     correct
default(omit)        -> defini=True   ->  firewall=0       silently wrong
valeur explicite     -> defini=True   ->  firewall=1       correct
```

`include_role` also refuses a templated dict for `vars:` (*"Vars in a IncludeRole must be specified as a
dictionary"*), so there is no conditional-key way out. Not exposing them keeps Proxmox's own defaults,
which is exactly what the devkit does when the caller omits them.

A card that needs those flags is best created then adjusted - or moved with `vm.replace.sdn_vnet`, which
**preserves** the firewall flag it read.

## Related

- `vm.replace.sdn_vnet` - move an existing card, preserving its model, its firewall flag and its id.
- `vm.detach.sdn_vnet` - remove a card.
- `vm.list.interfaces` - see what the VM has, and which slots are free.
- `vm.bootstrap` (the pre-existing bundle) already sets a VM's card at clone time via
  `vm_net_virtio_bridge`. No attach is needed during a normal deployment.
- the devkit equivalent: `proxmox_network.vm_id.add_interfaces_vm.to.jsons.sh`
