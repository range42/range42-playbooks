# sdn_network.bootstrap

Bring the declared SDN networks up on a Proxmox cluster: verify cluster coverage,
create missing objects, update explicit drift, apply **at most once when needed**,
then reconcile the live SNAT rules.

Use this bundle when a scenario supplies a declared network list. The direct-input
`sdn_network.bootstrap.sdn_vnet` bundle shares the same verified implementation
for one network. A scenario can import the list entrypoint as follows:

```yaml
- import_playbook: "{{ lookup('env', 'RANGE42_BUNDLE_DIR') }}/proxmox/sdn_network.bootstrap/main.yml"
  vars:
    BUNDLE_SDN_ZONE:  "{{ range42_sdn_zone }}"
    BUNDLE_SDN_VNETS: "{{ range42_sdn_vnets }}"
```

**Pass the two inputs in the `vars:` block ; do not rely on inheritance.** They could be reached by
ambient inheritance from the inventory, but then they would be *ambient values* - which the contract
rules say are not params at all - and `check-callsites.py` would report both as `PHANTOM` (declared,
never passed). Mapping the inventory's `range42_sdn_*` onto the bundle's `BUNDLE_SDN_*` at the
call-site is also what the naming plan prescribes for shared vars : map at the call-site, do not
rename globally.

The number of bundles in the catalogue is not the number of calls - same shape as
`cloud_init_image.download.*`, five bundles of which a scenario imports only the `.all`.

## Contract

| var | required | shape |
|---|---|---|
| `BUNDLE_SDN_ZONE` | yes | string - the zone holding every vnet below, created if absent |
| `BUNDLE_SDN_VNETS` | yes | list of `{ vnet, subnet, gateway, snat }` |
| `proxmox_node` | yes | read from the scenario vault, not passed at the call-site |

```yaml
BUNDLE_SDN_ZONE: r42
BUNDLE_SDN_VNETS:
  - { vnet: net142, subnet: 192.168.142.0/24, gateway: 192.168.142.1, snat: true }
  - { vnet: net143, subnet: 192.168.143.0/24, gateway: 192.168.143.1, snat: true }
```

`gateway` is optional: omission preserves an existing gateway, or leaves a new
subnet without one. An explicit gateway value participates in drift detection.
`snat` is optional and defaults to `true`, enabling subnet SNAT. A single-entry
list is supported.

The zone type is pinned to `simple` by the role (host-local, no VLAN, no VXLAN), so it is not a
parameter. Apply polling keeps the role defaults, 60 retries x 2s.

**Why `BUNDLE_` on the two inputs and not on `proxmox_node`.** The prefix marks what the CALLER
PASSES, and it exists for the backend: it will generate call-sites and inject its own variables into
a play whose variable space is FLAT and already holds group_vars, host_vars, scenario vars, vault
vars and role defaults. "Starts with `BUNDLE_`" is a rule a generator can apply without reading the
contract. `proxmox_node` is not passed - the play loads `default_vault.yml` and the role reads the
key - so it keeps its vault-key name. Full reasoning in
`______TODO_bundle-parameters-declaration_v6.md` section 9.

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

For a new zone, the operator inventory may set `sdn_zone_nodes` to a node list or
comma-separated node names. The same value feeds coverage planning and zone
creation. The controller sends a validated comma-separated API string for a
subset and omits the API field for empty/all-node scope. Existing zone membership comes from
the API and is not silently changed.

Target : `hosts: proxmox`, fixed. The reconciliation step runs on `proxmox_cli` - the role delegates
there itself, because the host carrying the API address is `ansible_connection: local` and an
undelegated shell would run on the deployer instead of the hypervisor.

## What it guarantees

- **A fully reconciled repeat writes nothing.** Matching declarations and live
  rules need no creation, update or apply. Missing enabled rules can require an
  apply, and surplus rules can require cleanup even when declarations match.
- **One apply per run, at most.** Never one per vnet.
- **The live rules match the declaration.** A subnet declared `snat: false` ends with zero SNAT
  rules even if one survived from an earlier state, and a subnet declared `snat: true` ends with
  exactly one, never two.

## Three design points worth knowing before editing this

**The apply is guarded, and that guard is load-bearing.** `PUT /cluster/sdn` runs `ifreload -a`,
which replays `/etc/network/interfaces` - including the legacy post-up MASQUERADE line of every
NAT-enabled `vmbr`. Each apply therefore adds one rule per legacy bridge. Measured, not deduced :
`936 -> 960` over 2 applies with 12 bridges. An unguarded apply on every run would inflate that
count forever, until the legacy sweep lands. Removing the `when:` would look harmless and would not
be.

**Reconciliation also runs when no apply is needed.** Fresh scope, coverage and
completion checks still guard every rule change. Reconciliation compares live
rules with the requested declaration, including rules left behind after SNAT
was disabled.

**Declaration writes loop over computed lists.** A folded `>-` scalar yields
a string, and the string `"False"` is truthy - a `when:` fed by a templated boolean fact is a trap
this project has already paid for. An empty list runs zero iterations and needs no boolean, so the
zone, though it is a single object, is carried as a list of zero or one.

## Two facts about the underlying actions

**The subnet id is derived for the comparison only.** Proxmox builds it as
`<zone>-<network>-<mask>`, so `192.168.142.0/24` in zone `r42` becomes `r42-192.168.142.0-24`. That
derivation is the only key the live list can be matched on. The create action does its own read-back
of the real id, so a divergence between the two would surface there rather than being assumed away.

**A live entry may LACK `subnet_gateway` or `subnet_snat`.** The role builds those dicts with `omit`
when the API did not return the field, and `omit` inside a `set_fact` dict drops the key rather than
leaving a placeholder string (verified against ansible-core, not assumed). Every read of those two
fields in `main.yml` therefore carries a `default()`, and removing one would make the diff compare
against an undefined value.

## Related

- `sdn_network.bootstrap.sdn_vnet` - the same sequence for **one** vnet, parameters given directly.
  Needs no data model, so it works before the SDN vnet declaration lands in the inventory (SDN plan T-15).
- `sdn_network.internet_on` / `.internet_off` / `.internet_toggle` - the snat axis alone, on an
  existing subnet.
- `sdn_network.delete` is **not** a bundle : the counterpart here is `sdn_network.delete.all`.
- `vm.bootstrap` already sets a VM's card on the right bridge at clone time, via
  `vm_net_virtio_bridge`. No attach bundle is called during a normal deployment.
