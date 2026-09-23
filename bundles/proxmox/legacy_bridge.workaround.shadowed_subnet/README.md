# legacy_bridge.workaround.shadowed_subnet

Frees a vnet's subnet from the legacy `vmbrNNN` bridge that shadows it. **Runtime only.**

## The problem

A `vmbrNNN` bridge and the `netNNN` vnet meant to replace it cannot both carry the same `.1`. If they do, the host resolves the subnet's route to the **bridge**, where no VM is attached, and ARPs into the void. Measured on a real host: the VM is unreachable, its NATed return traffic is lost, cloud-init ends `degraded` after minutes of timeouts, and SSH fails with `No route to host` - which reads like a timeout, not a routing fault.

Nothing in the SDN declaration is wrong. The zone, the vnet, the subnet, the gateway and the SNAT rule are all correct and stay correct. **No API check can see this** - the fault is in the host's routing table. The one command that tells you:

```bash
ip route get <the_vm_ip>      # must answer `dev netXXX`, not `dev vmbrXXX`
```

## What it does, and what it does not

`ip addr del` on the legacy bridge, for the declared subnet's address. Nothing else. **It writes nothing to disk**, so `ifreload -a` puts the address back - and every SDN apply runs `ifreload -a`.

That makes two things true. It must run **after** any apply, never before, or it is undone in the same second. And it is **not a fix**: for a durable one, use `legacy_bridge.cleaning.shadowed_subnet`, which removes the line from `/etc/network/interfaces`.

Its place is the host where you do not want to touch the disk yet - a production hypervisor, or a test before committing.

## On a clean host

Silent no-op. An absent bridge, or one that does not carry the address, is the normal answer and prints one line saying nothing was shadowed.

## The guard

A **running VM** attached to one of these bridges loses its gateway the moment the address goes. If that VM is the deployer, the play dies with it and you lose access mid-run. So the bundle lists the attached `tap` interfaces and **refuses**, naming them, rather than cutting anything off.

## Scope

Only the bridges that collide with a **declared** vnet. Stripping `vmbr145` while no `net145` exists would strand its VMs with no replacement.

## It proves its own effect

After freeing, it asks the host which device each declared subnet now leaves through, and fails if any still answers a `vmbr` - or nothing at all.

## Parameters

See `bundle_parameters.json`. `BUNDLE_SDN_VNETS` is the **same list** `sdn_network.bootstrap` takes, so a caller declares its networks once and passes it to both. The bridge and address are derived from each entry, never passed separately.

## Related

- `legacy_bridge.cleaning.shadowed_subnet` - the durable counterpart, edits the disk
- `sdn_network.bootstrap` - declares the vnets this bundle reads
