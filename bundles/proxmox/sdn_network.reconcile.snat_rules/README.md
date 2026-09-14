# sdn_network.reconcile.snat_rules

Reconcile a declared subnet's live SNAT rules on every applicable zone member,
or inspect its counts on every cluster node without changing rules.

## Inputs

| Variable | Required value |
|---|---|
| `BUNDLE_SDN_SUBNET_CIDR` | Canonical IPv4 CIDR, for example `192.168.199.0/24`; this is not the Proxmox subnet ID. |
| `BUNDLE_SDN_SNAT_WANT` | Integer `0`, `1`, or `99`, with the distinct behavior below. Strings, booleans and other numbers are refused. |
| `proxmox_node` | API coordinator node, read from the scenario vault. It does not limit cluster coverage. |

The matching controller requires a complete online cluster inventory, quorum
proof for multiple nodes, readable per-node task history, and a unique SSH
mapping from each node into `proxmox_cli`. A legitimate standalone node can use
the controller's single-node mapping default. Only supported simple zones and
legacy iptables are accepted. All-node snapshot coverage is required even when
the selected zone has fewer members.

## Reconcile: WANT 0 or 1

The CIDR must occur exactly once in the current declared subnets, with one
unambiguous VNet-to-zone binding. Its declared SNAT value must already equal
WANT. The bundle takes fresh cluster snapshots and uses the controller's stable
reconciliation guard to recheck membership, permissions and intervening
networking reloads before cleanup. Stale or incomplete proof cannot authorize
rule writes.

On applicable zone members, `0` removes exact-source SNAT/MASQUERADE rules and
`1` retains one. Unrelated rules, same-source non-NAT rules and all rules on
nonmember nodes are preserved. If any applicable node lacks an enabled rule,
the bundle refuses before cleanup: it cannot create the missing rule. Use the
reviewed bootstrap or internet-on flow to reconcile that declaration and apply
it. This bundle performs no declaration updates or SDN apply itself.

A deleted or ambiguous source cannot authorize cleanup. In particular, old
debug calls requesting WANT0 after deleting a subnet/VNet/zone now refuse;
orphan cleanup requires a retained, reviewed pre-delete source and node scope.
The separate `delete.all` entrypoint still needs that integration.

## Inspect: WANT 99

`99` is an explicit read-only mode, not a deletion threshold. It takes a fresh
complete cluster snapshot with no desired mutation sources and reports the
selected CIDR on every node, including when its SDN declaration has already
been deleted. No rule reconciliation, declaration write or apply is invoked,
regardless of the number of matching rules.

`network_count_snat_source` contains `source`, `primary_node`, `read_only: true`
and `nodes`, whose entries contain `node`, `count` and `captured_at`. These are
separate node observations, not an atomic cluster-wide measurement. Raw rules
are not included in the public count result.

For existing debug callers, `network_delete_extra_snat_rules.snat_before` and
`snat_after` remain aliases for the explicitly identified primary node's count.
That compatibility fact also includes the complete `nodes` list,
`snat_deleted: 0`, and `read_only: true`; it is not a cluster aggregate. Previous
metadata advertised arbitrary high WANT values as counters, but the matched
legacy helper accepts only 0/1. Only this explicit 99 path provides the
supported read-only counter contract.

## Operational limits

Use matching immutable playbooks and controller dependencies, including the
shared snapshot helper. External configuration writers must remain coordinated;
there is no cluster-wide transaction or atomic rollback. Counts are observations
at their per-node timestamps. This source checkpoint has local paired Ansible
coverage; matched live acceptance and the remaining deletion flow are pending.
