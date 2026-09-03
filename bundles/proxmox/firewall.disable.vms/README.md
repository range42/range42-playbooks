# firewall.disable.vms

Stop filtering every guest of the **active scenario**, and leave the way back in.

Same sequence as `firewall.disable.vm`, applied to every guest the scenario declares. Read that page for the reasoning; this one covers the sweep and its limits.

## The scope is the active scenario, and never another

Decision of the maintainer: other workspaces are not to be touched. The list comes from the scenario's own manifest, reached through the workspace:

```
$RANGE42_ACTIVE_CONFIG_DIR/scenario/manifest/scenario_vms.json
```

**The manifest shape is measured on all nineteen scenarios**, so this sweep works on any of them without one being modified: `vms` is a list in all 19, `vm_id` is present in **134 entries out of 134** and always an integer, and so are `vm_name`, `ip`, `role` and `bridge`. Only `group` is partial, 47 of 134, so nothing here relies on it.

**The templates are excluded.** They sit in their own list in the same file. A template never boots, so arming it filters nothing and only leaves a flag nobody asked for on a machine nobody runs.

**An empty scenario is a case, not an accident.** `debug_sdn_tests` declares zero guests. This bundle says so and stops, rather than reporting a success over nothing.

## The ssh accepts are posted, not deleted, and even here

One idempotent call per guest, and it guarantees that none of them can be armed later without a way in. Deleting them would build the dangerous asymmetry: a scenario full of disarmed guests whose next arming would be refused at best.

## This hands MAC spoofing back on the whole scenario at once

The card flag carries PVE's MAC anti-spoof as well, and the two cannot be separated. On a sweep, that is a whole scenario becoming spoofable in one run - which is either what a MITM exercise wants, or something to know **before** running it.

## Why the switches are not re-read at the end

The card read **accumulates**, so reading the cards of N guests gives all of them. The option read does **not** - it overwrites its fact, so a loop over N guests would keep only the last, and a verdict built on it would be a green that cannot fail. So this bundle does not build one.

What covers the switches is the action itself: each iteration carries the guard that refuses a guest whose ssh is not reachable, and **a failed iteration stops the whole run**. A green run therefore means every guest passed its own guard, one by one. The cards, which can be read collectively, **are** re-read and counted.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

## Not in scope

**The datacenter and the node.** Their switches keep whatever they had, and turning the datacenter off would stop filtering for every guest of **every** scenario at once - that is `firewall.disable.datacenter_and_nodes`.

## Related

- `firewall.disable.vm` - one guest, and the page that explains the reasoning.
- `firewall.enable.vms` - the mirror.
