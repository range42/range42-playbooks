# firewall.enable.vms

Arm every guest of the **active scenario**, card flags included.

Same sequence as `firewall.enable.vm`, applied to every guest the scenario declares. Read that page for why the order is what it is; this one covers the sweep and its limits.

## The scope is the active scenario, and never another

Decision of the maintainer: other workspaces are not to be touched. The list comes from the scenario's own manifest, reached through the workspace:

```
$RANGE42_ACTIVE_CONFIG_DIR/scenario/manifest/scenario_vms.json
```

**The manifest is a catalogue, not an inventory.** A scenario declares the guests it *can* deploy, and several of them are deployable on demand : an operator routinely chooses not to install some. A partially deployed scenario is therefore the normal case, not an accident.

So the sweep reads what is actually deployed on the node and keeps the intersection. **Declared guests that do not exist are skipped and named** : skipped in silence, one missing by mistake would be indistinguishable from one missing by choice. The report gives the three counts - declared, swept, absent.

Without that filter the first iteration aiming at an absent guest fails its API call and stops the whole run, leaving the following guests untouched. The reverse sweep would stop at the same place, so there would be no collective way to clean up either.

**The scope stays the active scenario, and only it.** The node listing returns every guest of the node, other workspaces included, but the intersection can only shrink the manifest list, never extend it. A guest id shared with another scenario is swept when the active manifest declares it, and ignored when it does not.

**Templates are dropped here too.** The node listing returns them as guests, and a template never boots.

**A scenario whose declared guests are none deployed stops the run** rather than reporting a success over nothing, the same way an empty scenario does.


**The manifest shape is measured on all nineteen scenarios**, so this sweep works on any of them without one being modified: `vms` is a list in all 19, `vm_id` is present in **134 entries out of 134** and always an integer, and so are `vm_name`, `ip`, `role` and `bridge`. Only `group` is partial, 47 of 134, so nothing here relies on it.

**The templates are excluded.** They sit in their own list in the same file. A template never boots, so arming it filters nothing and only leaves a flag nobody asked for on a machine nobody runs.

**An empty scenario is a case, not an accident.** `debug_sdn_tests` declares zero guests. This bundle says so and stops, rather than reporting a success over nothing.

## The sweep is phased, not per guest

All the accepts, then all the flags, then all the switches. That is what looping `include_role` allows, and it is safe because the only step that turns filtering on is the **last** one, and each of its iterations guards itself. A failure therefore leaves guests that are **not** filtered, never guests that are half armed.

## Why the switches are not re-read at the end

The card read **accumulates**, so reading the cards of N guests gives all of them. The option read does **not** - it overwrites its fact, so a loop over N guests would keep only the last, and a verdict built on it would be a green that cannot fail. So this bundle does not build one.

What covers the switches is the action itself: each iteration carries the guard that refuses a guest whose ssh is not reachable, and **a failed iteration stops the whole run**. A green run therefore means every guest passed its own guard, one by one. The cards, which can be read collectively, **are** re-read and counted.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

## Not in scope

**The datacenter and the node.** Nothing here filters until the datacenter switch is on, and the moment it is, **every** guest chain armed by this sweep comes alive at once.

## Related

- `firewall.enable.vm` - one guest, and the page that explains the order.
- `firewall.disable.vms` - the mirror.
- `firewall.enable.datacenter_and_nodes` - the switches this sweep depends on and does not touch.
