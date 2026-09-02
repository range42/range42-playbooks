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

## What the card firewall flag actually does, and why leaving it off is sometimes the point

The flag carries **two** features, not one, and Proxmox gives no way to separate them.

**Filtering.** It is one of three switches that must all be on before a single packet is filtered: the datacenter switch, the guest switch, and this flag. Any one of them off and nothing is filtered, whatever the other two say. A card with no flag is a card the firewall does not touch.

**MAC anti-spoof.** Measured from a root shell inside a guest: with `firewall=1` the guest becomes unreachable the moment it changes its MAC, while with the flag absent it stays reachable **on the fake address**. Setting the flag is the only thing that neutralises MAC spoofing - there is no second switch for it.

So the two readings of a card without the flag are both true at once: it is not filtered, and it can pretend to be another host at layer 2.

**In a cyber range that second half is often a feature, not a weakness.** A MITM or ARP-spoofing exercise needs the guest to be able to lie about its MAC, and a range that forbids it cannot teach it. That is why no bundle sets this flag today and why the default is to leave Proxmox's own default alone: a card created here can spoof, deliberately.

**What you cannot have is both.** Because one flag carries both features, a card cannot be filtered *and* allowed to spoof. Arming a card for isolation takes MAC spoofing away from the exercise running on it; leaving spoofing available means that card is not filtered at all. The choice is per card, so a scenario that needs both can put the spoofing exercise on its own card or its own guest.

## Related

- `vm.replace.sdn_vnet` - move an existing card, preserving its model, its firewall flag and its id.
- `vm.detach.sdn_vnet` - remove a card.
- `vm.list.interfaces` - see what the VM has, and which slots are free.
- `vm.bootstrap` (the pre-existing bundle) already sets a VM's card at clone time via
  `vm_net_virtio_bridge`. No attach is needed during a normal deployment.
- the devkit equivalent: `proxmox_network.vm_id.add_interfaces_vm.to.jsons.sh`
