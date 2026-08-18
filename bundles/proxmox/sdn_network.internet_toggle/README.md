# sdn_network.internet_toggle

Flip outbound internet for one subnet, whatever it is now. A composite, in three steps.

```
1. update_sdn_subnet   snat=toggle      the DECLARATION changes
2. apply_sdn                            the change reaches the running config
3. reconcile snat rules                 the LIVE iptables rules are brought in line
```

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_SDN_SUBNET_ID` | yes | `sdn_subnet_id` | the id Proxmox built, `<zone>-<network>-<mask>` |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

**One input only.** The vnet, the CIDR, the node and the current snat are read from
`list_sdn_subnets`. That is not laziness: the caller cannot pass a vnet/subnet pair that does not
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

**This is the only bundle of the 23 whose OUTCOME depends on the state it reads : the target is computed from the current snat, absent being read as 0. A caller that knows what it wants should use internet_on or internet_off instead - a toggle is for a human at a keyboard, not for a generated call whose result must be predictable.**

**The PUT does not resend the gateway.** Proxmox preserves the fields a PUT does not carry, so
resending them would only add a second way to get them wrong. Verified on real hardware in SDN plan
T-08.

**The reconciliation runs on the hypervisor.** The role delegates it to `groups['proxmox_cli'] | first`
and asserts the group is not empty - the host carrying the API address is `ansible_connection: local`,
so an undelegated shell would prune the deployer's own nat table. The inventory must define a
`proxmox_cli` group.

## Related

- `sdn_network.internet_on` / `.internet_off` / `.internet_toggle` - the three share ONE sequence and
  differ by a single line, the `_sdn_want` fact. They were produced from a single template so they
  could not drift; a change to the sequence must be made in all three.
- `sdn_network.update.sdn_subnet` - the raw declaration change, without the apply and without the
  reconciliation. Rarely what you want.
- `sdn_network.reconcile.snat_rules` - step 3 alone.
- the devkit equivalent, whose sequence this mirrors:
  `proxmox_network.sdn_subnet_id.toggle_outgoing_nat.to.jsons.sh`
