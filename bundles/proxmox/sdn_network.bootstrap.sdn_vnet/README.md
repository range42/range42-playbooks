# sdn_network.bootstrap.sdn_vnet

Bring one VNet and its subnet to the requested state using direct parameters.
This entrypoint and `sdn_network.bootstrap` use the same verified cluster flow:
the former supplies one network, while the latter supplies the caller's complete
`BUNDLE_SDN_VNETS` list.

## Contract

| Variable | Required | Meaning |
|---|---|---|
| `BUNDLE_SDN_ZONE` | yes | Simple zone holding the VNet; created if absent. |
| `BUNDLE_SDN_VNET` | yes | VNet name, also used as the guest bridge name. |
| `BUNDLE_SDN_SUBNET_CIDR` | yes | Canonical IPv4 source CIDR. |
| `BUNDLE_SDN_SUBNET_GATEWAY` | no | Explicit string gateway; omission preserves an existing gateway. |
| `BUNDLE_SDN_SUBNET_SNAT` | no | Integer `0` or `1`; defaults to `1`. |
| `proxmox_node` | yes | API coordinator from the scenario vault. |

An omitted gateway also leaves a newly created subnet without a gateway. An
explicit gateway or SNAT value that differs from the existing declaration is
reconciled. Invalid direct SNAT values are rejected before any network write.

The operator inventory must provide complete node-to-SSH mapping through
`sdn_snat_node_hosts` and `proxmox_cli`; the existing standalone-node default is
supported. New-zone `sdn_zone_nodes` membership is validated and encoded by the
controller. Existing VNet-to-zone bindings must agree with the requested zone.

## Execution

The shared flow reads declarations, verifies complete cluster snapshots and
source intent, then creates missing objects or updates drifted subnets. Creation
order remains zone, VNet, subnet. A verified snapshot is required before the
first declaration or rule write.

At most one global apply runs. Declaration changes or a missing enabled SNAT
rule on any applicable zone member can require that apply. An unchanged
request with the required live rules skips it. A stable request can still remove
surplus target rules through the verified no-apply reconciliation path.

The controller waits for verified reload completion on every covered node after
an apply. It reconciles the selected source only on zone members and preserves
unrelated/nonmember rules. Failed or unknown completion cannot authorize cleanup.
A missing enabled rule cannot be created by reconciliation alone.

## Input isolation

The two public entrypoints pass explicit private `_sdn_bootstrap_zone` and
`_sdn_bootstrap_networks` values into one shared task body. The direct entrypoint
never shadows or writes a global `BUNDLE_SDN_VNETS` fact. An ambient public list
therefore cannot change its explicit direct request or contaminate a later call.
Ordinary list bootstrap continues to process the full supplied list.

## Status and related entrypoints

This isolated source is not activated. See the
[remaining-entrypoint checkpoint](../../../docs/sdn-remaining-entrypoints-wip.md)
and [cluster integration limits](../../../docs/sdn-cluster-composites.md).
Standalone reconciliation and zone deletion remain separate pending work.

- `sdn_network.bootstrap` provides the same flow for a declared network list.
- `vm.attach.sdn_vnet` attaches a guest NIC after the network is available; compose
  the two calls explicitly when needed.
- `sdn_network.delete.all` is the zone-wide destructive counterpart and still
  requires the separate deletion contract review described in the handoff.
