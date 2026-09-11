# sdn_network.apply

Apply pending SDN configuration once, preserving untouched NAT source rules.

Every `sdn_network.create.*`, `.delete.*` and `.update.*` leaves its object **pending**; this is what
makes it real. A scenario does not call it - `sdn_network.bootstrap` applies once at the end of its own
sequence.

## Contract

| var | required | shape |
|---|---|---|
| `proxmox_node` | yes | read from the scenario vault, not passed at the call-site |
| `BUNDLE_SDN_CHANGED_SOURCES` | no | up to 64 unique canonical IPv4 CIDRs; default `[]` |

`PUT /cluster/sdn` applies all pending configuration. The changed-source list only
controls preservation of local NAT rules; it does not scope the global apply.

## Pending removal, replacement or reordering

Review pending changes and explicitly list every existing source CIDR whose
SNAT/MASQUERADE rules may change. For a subnet CIDR change, list both the old and
new CIDR. The list is validated before apply and recorded in the private snapshot;
restoration refuses a different policy after that snapshot.

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/proxmox/sdn_network.apply/main.yml"
  vars:
    BUNDLE_SDN_CHANGED_SOURCES:
      - 10.80.1.0/24
      - 10.80.4.0/24
```

For those exact source CIDRs, the result of pending configuration is retained,
including legitimate removal and reordering. This does not reconcile their count
to 0/1 or verify that pending configuration expresses the intended policy. Use
the existing explicit subnet reconciliation operation when that is required.

For every other existing source, preservation retains original argument
boundaries, rule shapes, order and multiplicities; only exact appended duplicate
NAT identities are deleted. A new rule shape for an existing untouched source
fails before cleanup. New source CIDRs may be retained when appended; otherwise
list them explicitly too. Non-NAT rules such as ACCEPT/LOG remain protected even
when their source CIDR is listed.

Unreviewed removal/reordering fails after apply without guessing a rollback.
Inspect the actual table and pending/running configuration before retrying; a
fresh snapshot cannot reconstruct a baseline lost in a previous failed apply.
Retain the original private snapshot for diagnosis without publishing raw rules.

## Current activation limits

This isolated preservation implementation is not ready for shared activation.
It requires the paired controller's reviewed snapshot implementation and a
verified legacy iptables backend. nft is refused before snapshot/apply. Only one
API coordinator is allowed; complete node-to-SSH coverage and successful reload
workers on every cluster node are required. See [the matched source checkpoint](../../../docs/sdn-cluster-composites.md).
No live SDN acceptance has been performed for this slice.

## The side effect to know before calling this in a loop

`PUT /cluster/sdn` returns a UPID; behind it Proxmox runs `reloadnetworkall`, which is `ifreload -a`.
That replays `/etc/network/interfaces` - including the legacy `post-up ... MASQUERADE` line of every
NAT-enabled `vmbr`. So **each apply adds one iptables rule per legacy bridge**. Measured, not deduced:
`936 -> 960` over 2 applies with 12 bridges.

Practical rule: write everything you have to write, then apply **once**. Do not apply "to be safe", and
never inside a loop. `sdn_network.bootstrap` guards its own apply behind a "did anything actually
change" test for this exact reason.

The preservation helper keeps existing unrelated multiplicities intact.
`sdn_network.reconcile.snat_rules` separately brings selected source rule counts
to their declared 0/1 values.

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
