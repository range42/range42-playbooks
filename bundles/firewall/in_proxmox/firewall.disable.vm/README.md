# firewall.disable.vm

Stop filtering one guest, and leave the way back in.

## The order is the mirror of the arming, and either step alone already does the job

```
1. the guest switch off  - the guest stops being filtered at once
2. the firewall flag off on its card, or on all its cards
```

All three conditions must hold for a single packet to be filtered, so removing any one of them is enough. That is why disarming is the easy direction and arming is not. The switch goes first anyway, because it is the one an operator reads.

## The ssh accept is posted, not deleted, and even on a disable

It costs one idempotent call - the action reads the chain before writing - and it guarantees that this guest can never be armed later without a way in, by this bundle or by anyone else.

Deleting it would build the dangerous asymmetry: a disarmed guest whose next arming would be refused at best, and would cut it at worst. If you want it gone, delete it explicitly.

## The flag is set to zero, not removed

Both produce the same observable effect, but they come from opposite intentions, and nobody can tell an isolation that was **declined** from one that was **lost**.

## Which cards

By default **all** the cards of the guest, mirroring the arming. Pass `BUNDLE_VM_VMNET_ID` to target exactly one - which is how you leave a guest filtered on one card and spoofable on another.

## The card flag carries two features, and they do not split

The same flag also carries PVE's **MAC anti-spoof**. Measured from a root shell inside a guest: with the flag set, the guest becomes unreachable the moment it changes its MAC; without it, it stays reachable **on the fake address**.

So a card is either **filtered** or **free to spoof**, never both. An administrator who wants a spoofable card - a MITM or ARP-spoofing exercise needs one - calls `proxmox_firewall.vm_id.disable_firewall_iface` directly. That is the only way to ask for it, and it costs that card its filtering.

## The verdict is read from the switch and from the cards

Both halves are asserted, and **separately**: a guest switch on with an unflagged card filters nothing, and a flagged card with the switch off filters nothing either. Reporting one without the other is how an operator ends up believing a guest is isolated when it is not.

Never from a return code: an action can apply its change and still fail afterwards, which happened during the measurement campaign and cost ten readings before the rule was adopted.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_VM_ID` | yes | `vm_id` | Proxmox VM id |
| `BUNDLE_VM_VMNET_ID` | no | `vm_vmnet_id` | which card, the N of `netN`. Default: **every card of the guest** |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

## Not in scope

**The datacenter and the node.** Their switches keep whatever they had, and turning the datacenter off would stop filtering for **every** guest at once - that is `firewall.disable.datacenter_and_nodes`.

## Related

- `firewall.enable.vm` - the mirror.
- `firewall.disable.vms` - the same sequence over every guest of the active scenario.
