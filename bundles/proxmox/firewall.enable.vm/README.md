# firewall.enable.vm

Arm one guest's firewall, card flag included, without cutting it off.

## Why this bundle exists

A guest is filtered only when **three** switches are all set: the datacenter one, the guest one, and the **per-card flag**. Any one of them off and not a single packet is filtered, whatever the other two say. Measured.

An operator who set only the guest switch would get a success and no filtering, with nothing to tell them why. This bundle sets all three that are its business, in the order that cannot lock anyone out.

## The order, and it is not a preference

```
1. the ssh accept on the guest's own chain
2. the firewall flag on its card, or on all its cards
3. the guest switch
```

**Accept first, always.** The guest switch **refuses** to arm a guest whose ssh is not accepted, active and above any deny that covers it. So arming before posting is refused by design, not by luck.

**The card flag before the switch.** Neither filters anything on its own, so the order between them is free - but doing the flag first means the last step is the one that turns filtering on, and a failure before it leaves a guest that is **not** filtered rather than one that is half armed.

**The ssh accept is posted every time, even when it looks redundant.** The action reads the chain before writing, so a second run posts nothing. It costs one call and removes the only way this bundle could make a guest unreachable.

## Only 22 is opened, and that is a bounded assumption

range42 deploys Linux guests today, and ssh is their only administration path. A guest whose admin path is RDP or WinRM would be cut **silently**.

| port | state |
|---|---|
| `22` | active - ssh |
| `3389` | commented in `main.yml` - RDP, for a future Windows guest |
| `5985` / `5986` | commented - WinRM, http and https |

The two other families are prepared as comments so that adding them is an uncommenting, not a rediscovery.

## Which cards

By default **all** the cards of the guest: a guest reachable through a second card that stayed unflagged is a guest that is not isolated. Pass `BUNDLE_VM_VMNET_ID` to target exactly one. A named card that does not exist is refused before anything is written.

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

**The datacenter and the node.** Their switches are `firewall.enable.datacenter_and_nodes`, and **nothing here filters until the datacenter one is on**. If it is off, the arming warns and the guest waits, armed but inert - and the moment the datacenter is armed, every guest chain comes alive at once.

## Related

- `firewall.disable.vm` - the mirror. Switch first, then the flag, and it keeps the ssh accept.
- `firewall.enable.vms` - the same sequence over every guest of the active scenario.
- `proxmox_firewall.vm_id.effective_filtering_state.to.jsons.sh` - reports all four levels with a verdict and the list of what is missing. Use it to see the state rather than infer it.
