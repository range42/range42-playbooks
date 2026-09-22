# sdn_network.update.sdn_subnet

Update the gateway or the NAT flag of an existing subnet. One raw API call.

**A scenario does not call this.** It calls `sdn_network.bootstrap`, which reads the live state, writes
only what differs, and applies once. This bundle exists for the backend-api and the deployer-ui, which
drive the family live one action at a time, and for driving a single object by hand.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_SDN_VNET` | yes | `sdn_vnet` | Name of the vnet. |
| `BUNDLE_SDN_SUBNET_ID` | yes | `sdn_subnet_id` | The subnet id Proxmox built, `<zone>-<network>-<mask>` - e. |
| `BUNDLE_SDN_SUBNET_GATEWAY` | no | `sdn_subnet_gateway` | Gateway of the subnet. |
| `BUNDLE_SDN_SUBNET_SNAT` | no | `sdn_subnet_snat` | 1 gives the guests outbound internet, 0 does not. |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

## Two things this bundle does NOT do

**It is not idempotent.** A second run fails on an object that already exists - the API answers
`500 already defined` - and deleting an absent object answers `500 does not exist`. Look the object up
first with the matching `sdn_network.list.*` bundle, or use a composite
(`sdn_network.bootstrap`, `sdn_network.delete.all`), which look up before writing and report a skip.

**It does not apply.** What it writes stays PENDING until `sdn_network.apply` runs. A read right after
this bundle shows the object with its `*_pending` key set. Nothing reaches the running network config
on its own.

## Worth knowing

For the NAT flag alone, prefer sdn_network.internet_on / .internet_off / .internet_toggle : they add the apply and the live-rule reconciliation that this raw update does not do, and a snat flipped without reconciliation leaves an orphaned iptables rule.

## Related

- `sdn_network.apply` - flush the pending config into the running one.
- `sdn_network.bootstrap` - the composite a scenario imports.
- `sdn_network.list.sdn_zones` / `.sdn_vnets` / `.sdn_subnets` - the reads that tell you whether the
  object is already there, and whether an apply is due.
- the devkit equivalent, for a shell one-liner rather than a playbook:
  `proxmox_network.*.update_sdn_subnet.to.jsons.sh`
