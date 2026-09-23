# sdn_network.reconcile.snat_rules

Bring the **live** iptables SNAT rules of one subnet down to a declared count. One action.

This is the only bundle of the family that looks at the **running** state rather than the declared one.
It reads the nat table on the hypervisor and deletes only what is in excess.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_SDN_SUBNET_CIDR` | yes | `sdn_subnet_cidr` | the CIDR **with** its mask, as iptables renders it - `192.168.199.0/24` |
| `BUNDLE_SDN_SNAT_WANT` | yes | `sdn_snat_want` | how many rules must remain - `1` for snat=1, `0` for snat=0 |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

`BUNDLE_SDN_SUBNET_CIDR` is the **CIDR**, not the Proxmox subnet id. The role asserts the shape and
refuses anything else, because that value is what anchors the rule match.

## Why this bundle exists

A subnet declared `snat=1` gets its MASQUERADE rule from the subnet's post-up hook. Two ways that goes
wrong, neither visible through the Proxmox API:

- **`ifreload -a` replays the hook**, and every apply runs it. Duplicates accumulate, one per apply per
  NAT-enabled bridge - `936 -> 960` over 2 applies with 12 bridges, measured.
- **Flipping `snat` to 0 removes the post-DOWN hook before it ever runs**, so the existing rule is
  orphaned: the declaration says no NAT, the kernel still NATs.

This action closes both. It is why `sdn_network.internet_on` / `.internet_off` run it after their
write, and why `sdn_network.bootstrap` runs it unconditionally at the end of every pass.

## It runs on the hypervisor, not on the deployer

The role delegates the iptables work to `groups['proxmox_cli'] | first` and **asserts the group is not
empty**. That delegation is load-bearing: the host carrying the API address is
`ansible_connection: local`, so an undelegated shell would count the deployer's own nat table and
cheerfully report zero. **The inventory must define a `proxmox_cli` group.**

## Two uses, one of them non-obvious

**Converge**: `want: 1` on a subnet declared `snat=1` leaves exactly one rule, however many had piled
up. `want: 0` on a subnet declared `snat=0` leaves none, including an orphan the API cannot see.

**Count without touching**: a `want` HIGHER than the live count makes this a pure counter - nothing is
in excess, so nothing is deleted, and the output still reports `snat_before`. That is how the SDN chain
test counts rules without perturbing them.

## Why `BUNDLE_SDN_SNAT_WANT` is required

The role defaults it to `1`, but this bundle demands it. Two reasons: reconciling to a target the caller
never stated is how a rule someone meant to keep gets deleted; and declaring it optional would mean
bridging it with `| default(omit)`, which **breaks** the role's default instead of preserving it - an
`include_role` var set to `default(omit)` arrives DEFINED-but-empty, so `| default(1)` never fires and
`want` lands empty. Verified against ansible-core.

## Related

- `sdn_network.internet_on` / `.internet_off` / `.internet_toggle` - flip the declaration AND
  reconcile, which is what you usually want.
- `sdn_network.apply` - the thing whose side effect makes this bundle necessary.
- the devkit equivalent: `proxmox_network.sdn_subnet_cidr.delete_extra_snat_rules.to.jsons.sh`
