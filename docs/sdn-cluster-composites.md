# Cluster SDN composite checkpoint — not activated

This source continuation pairs the playbooks preservation branch (starting at
`fb536e79ea969de6378e3cd272f75b878b0a03b3`) with controller
`932fdb4b02aed4d6612e648cdab318b77e8a64ff` (stable-path source
`4d14f3ccf64ba5ec16b4c5a49081e73794175292`, fixture correction `ed31eee`,
and validated zone-creation request encoding).
It preserves the existing Hyde integration; it does not update the installed
shared runtime or change any guest, SDN declaration, or firewall rule.

## Completed scope

`sdn_network.bootstrap`, `internet_on`, `internet_off`, `internet_toggle` and
`apply` now require current complete snapshot proof before their first write.
A shared task file clears old facts, requests the exact source/VNet/zone/desired
state and planned new-zone membership, and verifies snapshot and idle-baseline
keys cover the current plan. An older controller cannot silently ignore the
contract and continue with only its primary-node snapshot.

Bootstrap rejects a matching VNet bound to another zone; internet operations
resolve the selected VNet's authoritative zone before taking the snapshot.
New-zone `sdn_zone_nodes` uses the existing operator setting for both planning
and creation. Only simple zones are accepted by the controller planner.
Missing-enabled checks use every applicable node's snapshot, excluding nodes
outside the source's zone membership. Composite reconciliation calls
`network_reconcile_snat_sources` once with the saved plan; it does not reset
other sources to their current declarations.

A stable request does not claim an SDN apply occurred. Controller facts distinguish
verified snapshot/no attempted apply from attempted-and-verified completion.
Stable reconciliation refreshes membership, permissions and idle reload history.
Failed or unknown apply state is refused. After an actual apply, all covered
node reloads must complete before target reconciliation or preservation.

## Validation

All commands used the matching controller checkout through
`RANGE42_CONTROLLER_TEST_ROOT=/tmp/r42-sdn-controller-preservation-next-wave`:

```sh
python -m pytest -q tests/test_sdn_cluster_composites.py
python -m pytest -q tests/test_sdn_internet_reconciliation.py tests/test_sdn_scoped_nat_preservation.py
python -m pytest -q tests/test_sdn_paired_preservation.py
```

- 12 new real-Ansible/planner cases failed before implementation and then passed
  in 48.09s. They cover second-node missing rules, nonmember exclusion, new-zone
  membership, exact intent, stale/old/incomplete proof, and VNet binding refusal.
- 16 existing scoped composite cases passed in 52.59s after their single-node
  boundary fixtures were adapted to the current public contract.
- Two paired actual-controller cases passed in 32.23s. Only declaration/API I/O
  uses disposable fixtures; real task loops, planner, snapshot/restore helpers,
  per-node rules and completion guards run. Both stable internet-off and actual
  cluster-apply paths preserve unrelated rule identities/order and the target
  rule on the nonmember node. The fixture dispatch now matches the production
  role's supported action list, avoiding unrelated delegation during list reads.

These are 30 scoped playbooks checks, not a full repository or live cluster test.
Controller's preceding 61 checks (27 real Ansible) are separately recorded in
its `docs/sdn-cluster-coverage-wip.md`. The pytest asyncio default-loop
configuration warning remains. Scoped Ruff/formatting and whitespace checks
are recorded with the source checkpoint.

## Reviewed zone-creation follow-up

The initial paired boundary fixture did not inspect the actual zone POST. Review
caught a real mismatch: list-valued `sdn_zone_nodes` passed planner validation
but was forwarded as a JSON list where Proxmox expects a node-list string.
Controller `932fdb4` now validates current membership and the saved new-zone
scope, emits a comma-separated string for a subset, and omits `nodes` for empty
or all-node membership. Bootstrap's advertised list/string inputs now produce
the same node set in both planning and the actual request.

Three additional paired bootstrap tests execute the controller's actual zone
creation task over private loopback TLS and inspect the JSON body and planned
target nodes. List and empty cases failed before the fix; all three pass in
30.00s (`/tmp/r42-paired-zone-green.log`). The earlier two preservation cases were
deselected in that bounded command. Controller separately passed 40 checks
(11 actual request cases plus 29 existing planner cases). These request tests do
not create zones on a real Proxmox cluster. Scoped Ruff/formatting and whitespace
checks passed. No capability marker or installed runtime changed.

## Remaining activation limits

No capability marker is expanded by this change. The older
`bootstrap.sdn_vnet`, `delete.all`, and standalone `reconcile.snat_rules`
entrypoints still use their primary-node flows. They have not been adapted or
validated here; this paired branch must not be activated while those mutation
paths remain reachable without a separate guard/review. In particular, an
unsupported composite may write declarations before the newer controller
refuses its unproven apply.

Review all remaining entrypoints, node mapping changes and selected zone
membership changes before a matched release. Inventory SSH configuration is
operator managed; this code does not discover credentials. The shared helper
is an installed playbooks dependency and must be included in the immutable
runtime profile; copying just one bundle directory is insufficient.

The controller supports legacy iptables only; nft remains refused. Cooperating
legacy writers share a node-local transaction lock, but external configuration
writers still require coordination. The parent apply does not return child
UPIDs, so observed per-node workers are not a cryptographic parent-child proof.
There is no cluster-wide transaction or atomic rollback. Permission changes,
intervening reloads, disappeared task history and partial node failures require
inspection. Retain private snapshots for that inspection; do not publish rules
or credentials. Matched live single-/multi-node acceptance remains pending.
