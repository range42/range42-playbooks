# sdn_network.apply

Flush the pending SDN config into the running one. One action.

Every `sdn_network.create.*`, `.delete.*` and `.update.*` leaves its object **pending**; this is what
makes it real. A scenario does not call it - `sdn_network.bootstrap` applies once at the end of its own
sequence.

## Contract

| var | required | shape |
|---|---|---|
| `proxmox_node` | yes | read from the scenario vault, not passed at the call-site |

No caller-passed parameter: `PUT /cluster/sdn` takes no argument, it applies whatever is pending on the
cluster. **An apply cannot be scoped** - that is a property of the API.

## The side effect to know before calling this in a loop

`PUT /cluster/sdn` returns a UPID; behind it Proxmox runs `reloadnetworkall`, which is `ifreload -a`.
That replays `/etc/network/interfaces` - including the legacy `post-up ... MASQUERADE` line of every
NAT-enabled `vmbr`. So **each apply adds one iptables rule per legacy bridge**. Measured, not deduced:
`936 -> 960` over 2 applies with 12 bridges.

Practical rule: write everything you have to write, then apply **once**. Do not apply "to be safe", and
never inside a loop. `sdn_network.bootstrap` guards its own apply behind a "did anything actually
change" test for this exact reason.

Until the legacy bridges are gone, `sdn_network.reconcile.snat_rules` is what brings the rule count of
a given subnet back to its declared value.

## Why the polling knobs are not parameters

The role carries `sdn_apply_poll_retries | default(60)` and `sdn_apply_poll_delay | default(2)` - two
minutes of polling. Bridging them from the bundle with `| default(omit)` would **break** those defaults
rather than preserve them: an `include_role` var set to `default(omit)` arrives DEFINED-but-empty, so
the role's `| default(60)` never fires and `retries` lands empty. Verified against ansible-core.

Exposing them properly means duplicating the values in the bundle (`| default(60)`) and declaring them
`default_where: bundle-inline` - two places to keep in step. Not done until a caller asks.

## Related

- `sdn_network.list.sdn_zones` / `.sdn_vnets` / `.sdn_subnets` - their `*_pending` and `*_state` keys
  are how you know an apply is due.
- `sdn_network.reconcile.snat_rules` - bring the live SNAT rules of a subnet back to its declaration.
- `sdn_network.bootstrap` - the composite a scenario imports; one guarded apply per run.
- the devkit equivalent: `proxmox_network.datacenter.apply_sdn.to.jsons.sh`
