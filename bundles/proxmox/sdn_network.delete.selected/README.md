# sdn_network.delete.selected

Delete only named VNets and every authoritative live subnet attached to them.
The explicit zone remains, including when its last selected VNet is removed.
Other VNets in that same zone, their guest attachments and their rules remain
outside deletion scope. Names and subnet IDs never imply a source CIDR.

## Inputs and CLI adapter

- `BUNDLE_SDN_ZONE`: the explicit simple zone. Every existing selected VNet must
  belong to it. Different-zone selections refuse the operation.
- `BUNDLE_SDN_VNETS`: a nonempty list of at most 64 unique valid VNet names.
- `BUNDLE_SDN_DELETE_READ_ONLY`: optional boolean, default false.
- `proxmox_node`, API credentials, TLS policy and node-to-SSH mapping: the same
  controller inventory/vault contract as `sdn_network.delete.all`.
- `RANGE42_SDN_DELETE_STATE_DIR`: the same stable, private per-cluster state root
  used by every normal deletion attempt. It must not be a fresh attempt folder.

The existing scenario command now invokes `00_sdn_bootstrap/delete.yml` using
`RANGE42_ANSIBLE_ROLES__INVENTORY_DIR/inventory_default.yml` and
`RANGE42_VAULT_PASSWORD_FILE`, matching its setup companion. The YAML adapter
reads `manifest/scenario_vms.json`, selects unique `net*` names from the existing
VM/template `bridge` fields and uses the setup declaration's
`range42_sdn_zone | default('r42zone')`. Legacy `vmbr*` fields are ignored; IPs
are never used to select a network. Missing or malformed manifests and an empty
selection refuse the operation. Extra NIC expansion is not inferred by this
legacy manifest adapter.

```sh
./blank_scenario_2_sdn.delete_networks.sh --dry-run
./blank_scenario_2_sdn.delete_networks.sh
```

Other Ansible arguments are forwarded. `--dry-run`, `--check` and `-C` select the
explicit read-only path; native Ansible check mode is removed because it would
skip the commands needed to prove current scope. Preview performs complete
privileged declaration/guest reads and API/SSH cluster identity checks. It does
not write declarations, trigger apply, modify rules or create/update a journal.
It also does not check mutation admission or collect rule snapshots, and says so
in its report. It is an observation, not retained authorization for a later write.

## Shared guarded flow

Both deletion bundles use `_shared/sdn_delete.yml`. The default whole-zone
bundle still removes all matching subnets, VNets and the zone. The selected
wrapper passes an explicit list and suppresses only the zone removal operation;
it does not bypass any normal mutation guard.

Normal execution checks incomplete journals before treating absent selected
objects as a no-op, then validates complete privileged current/pending QEMU/LXC
scope, settled global SDN families, canonical CIDRs, unique source/VNet/zone
bindings and matching API/SSH cluster identity. Any selected current or pending
NIC attachment refuses deletion. No guest is detached automatically.

Before the first declaration write, all cluster nodes have verified rule
snapshots and idle reload baselines, and a fresh privileged scope must match.
The durable journal retains the exact requested selection, actual live objects,
source intent, original membership and snapshots. It shares the existing
cluster-wide admission mechanism with whole-zone deletion; an incomplete record
blocks another selection or zone. No selected operation can resume an incomplete
record by supplying a different list.

Deletion proceeds through selected subnets, then selected VNets. One global apply
must complete on every covered node before zeroing removed source rules on their
original members and restoring exact non-target/nonmember rule identities and
order. Final inventory hashing requires the zone and every unselected declaration
to remain exactly as observed. Missing selected names carry no inferred CIDRs;
an absent repeat performs no apply or orphan-rule cleanup.

Partial failure retains the same durable before/after request evidence and
blocks blind retries. Automatic resume or rollback is not implemented. The
existing external-writer coordination, legacy-iptables-only support, bounded
collector and journal limits remain in force; see
[the whole-zone contract](../sdn_network.delete.all/README.md).

This is source-only local acceptance. Matching controller/playbooks dependencies
are required before a reviewed release. No live deletion or rollout is claimed.
