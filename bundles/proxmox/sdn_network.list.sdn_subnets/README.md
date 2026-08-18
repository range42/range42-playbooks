# sdn_network.list.sdn_subnets

Read the SDN subnets of the cluster. One action, no write, no apply.

**A scenario does not call this.** It calls `sdn_network.bootstrap`, which reads the state itself
before deciding what to write. This bundle exists for the backend-api and the deployer-ui, which
drive the sdn_network family live, one action at a time - and for debugging by hand.

## Contract

| var | required | shape |
|---|---|---|
| `proxmox_node` | yes | read from the scenario vault, not passed at the call-site |

No caller-passed parameter: `GET /cluster/sdn/vnets/{vnet}/subnets, once per vnet` is cluster-level and returns
everything. Filtering is the consumer's job, on the resulting fact.

## Output

The role sets the fact **`network_list_sdn_subnets`** - a list holding one dict per subnet - and prints
it. Keys per entry:

```
subnet
subnet_vnet
subnet_cidr
subnet_type
subnet_zone
subnet_gateway
subnet_snat
subnet_dhcp_range
subnet_dhcp_dns_server
subnet_pending
subnet_state
```

`subnet` is the ID Proxmox built (`<zone>-<network>-<mask>`) and `subnet_cidr` is the network - the two are never the same string, do not confuse them. `subnet_snat` is 1 when the guests get outbound internet.

Two traps worth knowing before consuming this fact.

**A key is ABSENT when the API did not return the field.** The role builds these dicts with `omit`,
and `omit` inside a `set_fact` dict DROPS the key rather than leaving a placeholder string (verified
against ansible-core). So `subnet_state` or `subnet_pending` may simply not be there, and any
comparison needs a `default()` or it compares against an undefined value.

**The fact is REBUILT on each call, it does not accumulate.** That is a property of the three SDN list
actions specifically. `network_list_interfaces_vm` behaves the opposite way - it appends - so calling
it twice in one run doubles its content. Do not generalise from one to the other.

## Reading whether an apply is due

`subnet_pending` and `subnet_state` are what tell you the running config has not caught up with the
declared one. A freshly written object stays pending until `sdn_network.apply` runs.

## Related

- `sdn_network.apply` - flush the pending config into the running one.
- `sdn_network.bootstrap` - the composite a scenario imports; reads, diffs, writes, applies once.
- the devkit equivalent, for a shell one-liner rather than a playbook:
  `proxmox_network.datacenter.list_sdn_subnets.to.jsons.sh`
