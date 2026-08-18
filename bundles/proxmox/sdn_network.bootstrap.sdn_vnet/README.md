# sdn_network.bootstrap.sdn_vnet

Bring up **one** vnet with its subnet, parameters given directly.

## The difference with `sdn_network.bootstrap` is not "all versus one"

It is **where the parameters come from**:

| bundle | input |
|---|---|
| `sdn_network.bootstrap` | loops over the DECLARED list `BUNDLE_SDN_VNETS` - the data model |
| `sdn_network.bootstrap.sdn_vnet` | takes zone / vnet / subnet **directly** |

So this one needs no data model and **works today**, before the declaration lands in the inventory. That
makes it the bundle for a fresh Proxmox, and for the backend's "on the fly" case: one network, stated on
the spot.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_SDN_ZONE` | yes | `sdn_zone` | zone holding the vnet, created if absent |
| `BUNDLE_SDN_VNET` | yes | `sdn_vnet` | vnet name - the name a VM uses as its bridge |
| `BUNDLE_SDN_SUBNET_CIDR` | yes | `sdn_subnet`, `sdn_subnet_cidr` | the CIDR, e.g. `192.168.142.0/24` |
| `BUNDLE_SDN_SUBNET_GATEWAY` | no | `sdn_subnet_gateway` | optional - a subnet without one is legal |
| `BUNDLE_SDN_SUBNET_SNAT` | no | `sdn_subnet_snat`, `sdn_snat_want` | `1` outbound internet, `0` not. Default `1` |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

`BUNDLE_SDN_SUBNET_CIDR` is used **twice**: to create the subnet, and to anchor the reconciliation, which
matches on the source network. Same for `BUNDLE_SDN_SUBNET_SNAT`, which drives the declaration *and* the
number of live rules left behind - which is why the two always agree.

## The sequence, and the order Proxmox imposes

```
zone (if absent) -> vnet (if absent) -> subnet (if absent) -> apply ONCE -> reconcile the live rules
```

A vnet cannot be created before its zone, nor a subnet before its vnet.

## What it guarantees

**A second run writes nothing.** Each object is looked up before being written. The raw create actions
answer `500 already defined` on a second run; tolerating that 500 would mean matching an error string and
would also swallow real failures. So absence is established by a **read**.

**One apply per run, at most**, and only if something was written. `ifreload -a` - which the apply runs -
replays the legacy post-up MASQUERADE lines, so each apply adds one iptables rule per NAT-enabled `vmbr`.
Measured: `936 -> 960` over 2 applies with 12 bridges. Removing that `when:` would look harmless and
would not be.

**The live rules match the declaration.** The reconciliation is deliberately **not** guarded: it is the
only thing that proves it, and a rule that outlived its declaration is invisible to the API.

## Two implementation notes

**No boolean fact drives anything.** A folded `>-` scalar yields a string, and the string `"False"` is
truthy. Every step loops over a computed list - empty means zero iterations - and the apply's `when:` is a
length comparison.

**The subnet id is derived only to recognise the object** in the live list. Nothing this bundle writes is
addressed by a computed value.

## Related

- `sdn_network.bootstrap` - the same sequence driven by the declared list; what a scenario imports.
- `vm.attach.sdn_vnet` - to put a VM card on the vnet once it is up. For the case of a VM deployed onto a
  vnet that may not exist yet, CHAIN the two at the call-site rather than looking for a wrapper bundle :

  ```yaml
  - import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/proxmox/sdn_network.bootstrap.sdn_vnet/main.yml"
    vars: { BUNDLE_SDN_ZONE: ..., BUNDLE_SDN_VNET: ..., BUNDLE_SDN_SUBNET_CIDR: ... }
  - import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/proxmox/vm.attach.sdn_vnet/main.yml"
    vars: { BUNDLE_VM_ID: ..., BUNDLE_VM_VMNET_ID: ..., BUNDLE_VM_IFACE_BRIDGE: ... }
  ```

  A wrapper bundle was written and retired : composing inside a bundle cannot repass a parameter under its
  own name (`AAA: "{{ AAA }}"` is a recursive loop), so the values had to travel by inheritance - and the
  annotation checker, which reads the call-site `vars:` block, then reported them as never passed. Chaining
  at the call-site fills that block, so the contract stays checkable.
- `sdn_network.delete.all` - the delete counterpart, zone-scoped.
- the devkit equivalent: `proxmox_network.datacenter.create_sdn_network.to.jsons.sh`
