# vm.list.interfaces

Read the network cards of one VM. One action.

**Subject `vm`, not `sdn_network`**, on purpose: this reports every card, on an SDN vnet or on a legacy
`vmbr` alike. It knows nothing about SDN.

## Contract

| var | required | role var | shape |
|---|---|---|---|
| `BUNDLE_VM_ID` | yes | `vm_id` | Proxmox VM id |
| `proxmox_node` | yes | - | read from the scenario vault, not passed at the call-site |

Unlike the SDN endpoints, this one **is** node-scoped: the VM must live on `proxmox_node`.

## Output

The role sets the fact **`network_list_interfaces_vm`** - one dict per card:

```
vm_id  vm_network_device (netN)  vm_vmnet_id (the N, an int)  vm_network_type (the model)
vm_network_mac  vm_network_bridge  vm_network_firewall
```

`vm_vmnet_id` is the id a delete or a replace addresses. Its absence from this output used to be a real
defect (fixed under PXC #124/#125) - that fix is what makes this output usable as the input of a write.

`vm_network_firewall` is **absent** when the card carries no firewall flag: the role builds the dict with
`omit`, which drops the key. Compare it with a `default()` or you compare against undefined.

## The fact ACCUMULATES - this bundle resets it first

`network_list_interfaces_vm` is built as `(network_list_interfaces_vm | default([])) + [..]`. It
**appends**. Called twice in one run - which `vm.replace.sdn_vnet` does - it would return each card
twice; a consumer picking `[0]` would still look right, a consumer counting would not. Hence the
`set_fact: []` before the read, which is not optional.

**The three `sdn_network.list.*` actions behave the opposite way**: they rebuild their fact from
scratch. Do not generalise from one family to the other.

## Related

- `vm.attach.sdn_vnet` / `vm.detach.sdn_vnet` / `vm.replace.sdn_vnet` - the writes this read feeds.
- the devkit equivalent: `proxmox_network.vm_id.list_interfaces_vm.to.jsons.sh`
