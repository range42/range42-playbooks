# sdn_network.delete.all

Tear down one zone completely: its subnets, its vnets, the zone itself.

**Zone-scoped, and driven by what is live** - not by a declaration. It reads the cluster, then removes
what belongs to the named zone. So it works on a state nobody declared, which is exactly when a teardown
is needed.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_SDN_ZONE` | yes | `sdn_zone` | the zone to wipe |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

**One parameter, and that is the safety property.** The scope of a destructive action is a single explicit
zone. Nothing outside it is read, nothing outside it is touched, and there is no wildcard or "all zones"
mode to reach by mistake.

## The order is imposed by Proxmox, not chosen

```
subnets -> vnets -> zone -> apply -> reconcile every removed subnet to want=0
```

A vnet still holding a subnet cannot be removed, nor a zone still holding a vnet.

## What it will NOT do for you: detach a VM

Proxmox also refuses to delete a vnet that still carries a **VM network card**, and this bundle does not
hunt for those - a VM is not part of a network's declaration. If a card is still attached, the vnet delete
fails and the failure names the **vnet** rather than the card.

Detach first with `vm.detach.sdn_vnet`, or move the card with `vm.replace.sdn_vnet`.

## Why the reconciliation matters more here than anywhere

Deleting a subnet removes its post-down hook from the configuration **before that hook ever runs**. The
live MASQUERADE rule therefore survives the object that declared it: the subnet is gone and the kernel
still NATs its network. No API read shows this.

`want=0` per removed subnet is what closes it, and it runs **after** the apply so the post-down has had
its chance first.

A subnet with no readable `subnet_cidr` is **skipped** rather than reconciled blindly - a missing anchor
would match nothing, or everything.

## Two implementation notes

**The subnets are scoped through `subnet_vnet`, not `subnet_zone`.** The role emits `subnet_zone` with
`omit`, so the key is **absent** whenever the API did not return it - and filtering on a key that may not
exist would silently scope the teardown to nothing. So: the vnets of the zone come from `vnet_zone`, and
the subnets come from `subnet_vnet` being one of those vnets.

**Nothing is addressed by a computed value.** Every subnet id and vnet name passed to a delete comes from
the read.

## Idempotent by lookup

A second run finds nothing to remove, writes nothing, skips the apply - and still reconciles.

## Related

- `sdn_network.bootstrap` / `.bootstrap.sdn_vnet` - the build counterparts.
- `sdn_network.delete.sdn_subnet` / `.sdn_vnet` / `.sdn_zone` - the raw single deletes, unordered and
  unapplied.
- `vm.detach.sdn_vnet` - what frees a vnet still carrying a card.
- the devkit equivalent: `proxmox_network.datacenter.delete_sdn_network.to.jsons.sh`
