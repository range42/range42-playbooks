# firewall.enable.vms

Arm every guest of the **active scenario**, card flags included.

Same sequence as `firewall.enable.vm`, applied to every guest the scenario declares. Read that page for why the order is what it is; this one covers the sweep and its limits.

## The scope is the active scenario, and never another

Decision of the maintainer: other workspaces are not to be touched. The list comes from the scenario's own manifest, reached through the workspace:

```
$RANGE42_ACTIVE_CONFIG_DIR/scenario/manifest/scenario_vms.json
```

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
