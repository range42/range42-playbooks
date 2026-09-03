# firewall.disable.datacenter_and_nodes

Turn the host firewall off, and leave the way back in.

## The order is the mirror of the arming, and the first step is the one that matters

```
1. the DATACENTER switch off - everything stops filtering at once, at every level
2. the NODE switch off
```

The datacenter switch is the **master**: with it off, nothing is installed anywhere - not the host chain, not a single guest chain - whatever the other switches say. Measured. So the first task already does the whole job and the second only tidies up.

**This is why disarming is the safe direction and arming is not.** One step, one effect, no ordering trap.

## The management accepts are not deleted, and that is deliberate

Leaving them costs nothing: a rule in a chain that is not installed has no effect. And it keeps any later arming safe.

Deleting them would build the dangerous asymmetry - a disarmed host whose next arming, by the mirror bundle or by anyone else, would have no accepted path and would be refused at best. If you want them gone, delete them explicitly. Do not make it a side effect of switching off.

## What this does not do

**It does not disarm the guests.** A guest keeps its own switch and its card flag; they stop filtering only because the datacenter is off.

Turn the datacenter back on and **every guest chain comes alive again, all at once**. Cause and effect are separated in time, which is exactly the trap the guest bundles exist to handle: a guest without an active accept on its admin port loses that access at the moment the datacenter is armed, not when its rule was posted.

## The verdict is read from the switches

The last tasks read both switches back and the run fails if either stayed on. The datacenter one is the load-bearing assertion: while it reads `1`, filtering continues at every level. The node is asserted too, because leaving it on after a disable is an inconsistent state that would surprise the next reader - not because it filters anything by itself.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

**No caller-passed parameter.** Switching off takes no tuning: there is nothing to choose. The mirror bundle hides three knobs; this one hides an order.

## Related

- `firewall.enable.datacenter_and_nodes` - the mirror. Accepts first, then the datacenter, then the node.
- `proxmox_firewall.vm_id.effective_filtering_state.to.jsons.sh` - the devkit that reports all four levels with a verdict and the list of what is missing.
