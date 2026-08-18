# sdn_network.bootstrap

Bring the declared SDN networks up on a Proxmox cluster : read the live state, create what is
missing, update what has drifted, apply **once**, then reconcile the live SNAT rules.

**This is the only `sdn_network.*` bundle a scenario calls.** The others expose a single action
each, for the backend-api and the deployer-ui to drive live, and for debugging. A scenario needs
one line :

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

`gateway` is optional - a subnet without one is legal. `snat` is optional and defaults to `true`;
it is what gives the guests outbound internet. A **single-entry list** is the "on the fly" case the
backend uses, and behaves exactly the same.

The zone type is pinned to `simple` by the role (host-local, no VLAN, no VXLAN), so it is not a
parameter. Apply polling keeps the role defaults, 60 retries x 2s.

**Why `BUNDLE_` on the two inputs and not on `proxmox_node`.** The prefix marks what the CALLER
PASSES, and it exists for the backend: it will generate call-sites and inject its own variables into
a play whose variable space is FLAT and already holds group_vars, host_vars, scenario vars, vault
vars and role defaults. "Starts with `BUNDLE_`" is a rule a generator can apply without reading the
contract. `proxmox_node` is not passed - the play loads `default_vault.yml` and the role reads the
key - so it keeps its vault-key name. Full reasoning in
`______TODO_bundle-parameters-declaration_v6.md` section 9.

Target : `hosts: proxmox`, fixed. The reconciliation step runs on `proxmox_cli` - the role delegates
there itself, because the host carrying the API address is `ansible_connection: local` and an
undelegated shell would run on the deployer instead of the hypervisor.

## What it guarantees

- **A second run writes nothing.** A declared object already live in the declared shape appears in
  none of the four diff lists, so no create and no update runs, and the apply is skipped.
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

**The reconciliation is deliberately NOT guarded.** It is the only thing that proves the live rules
match the declaration, and it is cheap : it reads the nat table and deletes only the surplus. A rule
that outlived its declaration is invisible to any API read and visible only here. Same choice as the
devkit composite, for the same reason.

**Every step loops over a computed list rather than carrying a `when:`.** A folded `>-` scalar yields
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
- `sdn_network.teardown` is **not** a bundle : the counterpart here is `sdn_network.delete.all`.
- `vm.bootstrap` already sets a VM's card on the right bridge at clone time, via
  `vm_net_virtio_bridge`. No attach bundle is called during a normal deployment.
