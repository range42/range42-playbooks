# sdn_network.internet_on

Turn outbound internet ON for one subnet. A composite, in three steps.

```
1. update_sdn_subnet   snat=on      the DECLARATION changes
2. apply_sdn                            the change reaches the running config
3. reconcile snat rules                 the LIVE iptables rules are brought in line
```

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_SDN_SUBNET_ID` | yes | `sdn_subnet_id` | the id Proxmox built, `<zone>-<network>-<mask>` |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

**One input only.** The VNet, CIDR and current snat are read from
`list_sdn_subnets`; `list_sdn_vnets` supplies the authoritative zone binding. That is not laziness: the caller cannot pass a vnet/subnet pair that does not
exist, and the read doubles as the subnet's existence proof - so a wrong id fails with a message
naming the problem instead of a bare API `500`.

`BUNDLE_SDN_SUBNET_ID` is the **id**, not the CIDR. Do not derive it by hand: a zone name may itself
contain dashes. List the real ones with `sdn_network.list.sdn_subnets`.

## Why three steps and not one

**`ifreload -a` replays the post-up hook.** The apply runs it, so a subnet at `snat=1` gains a
duplicate MASQUERADE rule on every apply.

**Turning snat off orphans the existing rule.** Setting `snat=0` removes the post-DOWN hook from the
configuration *before that hook ever runs*, so the live rule survives its own declaration: the
declaration says no NAT, the kernel still NATs.

Neither is visible through the Proxmox API. Step 3 is what closes both, and it runs
**unconditionally** - even when the declaration was already at the wanted value, because the
declaration may be right while the live rules are not.

## Worth knowing

**If the subnet is already at snat=1 the chain still runs, and that is deliberate : the declaration may be right while the LIVE rules are not.**

**The PUT does not resend the gateway.** Proxmox preserves the fields a PUT does not carry, so
resending them would only add a second way to get them wrong. Verified on real hardware in SDN plan
T-08.

## Cluster snapshot contract

These composites require the paired controller's verified cluster snapshot
contract. Configure one API coordinator and complete `sdn_snat_node_hosts`
node-to-host mapping into `proxmox_cli`; the single-node/single-SSH-host case can
use the controller default. Every cluster node must be online, reachable and
visible with effective `Sys.Audit` on its node path. Only simple SDN zones are
supported.

The snapshot records exact `{source, vnet, zone, want}` intent before the first
write. Existing VNet zone bindings come from the API. Reconciliation changes a
source only on its zone members, while snapshot and post-apply preservation cover
every node. A missing enabled rule on any applicable node can require one apply.
Stable requests use a verified no-apply path; a failed or unverified apply never
authorizes cleanup. See [the matched source checkpoint](../../../docs/sdn-cluster-composites.md)
for tests and activation limits.

## Related

- `sdn_network.internet_on` / `.internet_off` / `.internet_toggle` - the three share ONE sequence and
  differ by a single line, the `_sdn_want` fact. They were produced from a single template so they
  could not drift; a change to the sequence must be made in all three.
- `sdn_network.update.sdn_subnet` - the raw declaration change, without the apply and without the
  reconciliation. Rarely what you want.
- `sdn_network.reconcile.snat_rules` - step 3 alone.
- the devkit equivalent, whose sequence this mirrors:
  `proxmox_network.sdn_subnet_id.enable_outgoing_nat.to.jsons.sh`
