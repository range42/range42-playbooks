# Remaining SDN entrypoints — source checkpoint, do not activate

The user requested a checkpoint because usage was nearly exhausted. This work
starts from playbooks `c5c9567f217b316c6ccc5ba04ae0cbf0e223318d`, paired with
controller `92e68c91f63cba64ad304d2e2c3f750320db6c16`. No controller, installer,
live VM, network, firewall, release, or provider state was changed in this slice.
No source was pushed.

## Work currently present

The direct-parameter `bootstrap.sdn_vnet` entrypoint validates its direct inputs
and passes a normalized private input into the shared bootstrap task body. It requires integer
SNAT 0/1 and an optional string gateway before entering that flow. This removes
the separate primary-node-only mutation sequence. The shared bootstrap now
compares gateway drift only when the caller explicitly supplies a gateway;
omission preserves an existing gateway without a pointless update/apply.

Six initial single-VNet regressions failed against the old entrypoint (missing
coverage, foreign binding, missing-enabled rules, stable flow and actual new-zone
POST intent), log `/tmp/r42-sdn-entrypoints-red.log`. Two further regressions
failed for omitted-gateway shared-bootstrap idempotence and invalid direct SNAT;
the existing single-VNet omitted-gateway case already passed, log
`/tmp/r42-sdn-adapter-red.log`.

The already-running focused command finished **9 passed, 1 failed in 51.02s**,
exit1 (handle46499), log `/tmp/r42-sdn-entrypoints-green.log`. The filename is a
prospective log label, not a passing result. The failing regression is
`test_single_vnet_explicit_off_maps_to_disabled_declaration_and_intent`: an outer
`BUNDLE_SDN_VNETS` variable overrides the imported adapter's generated list, so an
explicit direct SNAT0 request incorrectly produces want1. This is a real input
precedence bug; the fixture must not be weakened to hide it.

The explicitly resumed continuation fixes this precedence bug by giving both
wrappers one shared task body with private `_sdn_bootstrap_zone` and
`_sdn_bootstrap_networks` include variables. No global public bundle-input fact
is written. The ambient-list/SNAT0 regression remains, alongside a two-network
ordinary-list regression. The original entrypoint source is retained by Git at
the base commit. This source has not been activated. The resumed affected run
(handle6079) completed exit0: **26 passed, 15 deselected in 138.88s**, log
`/tmp/r42-sdn-adapter-private-input-green.log`. It includes the unchanged ambient
list/SNAT0 regression, ordinary two-network list behavior, gateway omission,
cluster coverage/binding refusal, and actual paired zone POST checks. Controller
source was unchanged; no additional controller suite was run. Independent review
confirmed the extracted task body differs only in its private input names,
include path/header and the intended explicit-gateway drift condition.

The pause was honored by saving WIP commit `01e4566`; the subsequent explicit
continuation authorized only this input-isolation fix and its affected checks.
The single-VNet README now describes gateway omission, explicit gateway/SNAT
drift and missing-enabled-rule applies. Scoped Ruff and whitespace checks pass.
The subsequent metadata checkpoint `92544e4` updates both bootstrap descriptors
and generated JSON to the reviewed behavior. Treat this as source work, not a
deployable matched release; the deletion integration below remains pending.

## Standalone reconciliation continuation

The next authorized slice starts from playbooks `6cf9a0d` and controller
`92e68c9`, with the independent bootstrap metadata checkpoint `92544e4`
retained. The matching controller count action is committed at
`2f35a76d15ac273f8439e97920d86cbd8f127e14`. `reconcile.snat_rules` now has two
explicit modes:

- Integer WANT0/1 requires exactly one current CIDR-to-VNet-to-zone binding
  and a matching declared SNAT state. It takes complete current cluster
  snapshots, refuses any missing enabled rule before cleanup, and uses the
  controller's stable no-apply reconciliation. Only applicable zone members
  change; unrelated and nonmember rule identities/order remain intact.
- WANT99 is strictly read-only. It snapshots every mapped node with no desired
  mutation sources, validates the complete receipt set and reports only the
  source/count/node/timestamp fields. Counts also work after declarations are
  deleted and when a node has more than 99 matching rules. Legacy `snat_before`
  and `snat_after` aliases refer explicitly to the primary node; the full node
  list and `read_only: true` remain visible. Node observations are not an
  atomic measurement. The old bundle metadata advertised arbitrary high WANT
  counters, but the matched legacy helper actually refuses values other than
  0/1; the new explicit mode repairs that compatibility.
- Debug `07d-attach_second_card.yml` requests WANT0 after raw subnet/VNet/zone
  deletion. Fresh authoritative binding is then unavailable, so cleanup must
  refuse. A retained, reviewed pre-delete membership contract remains deletion
  work; this change does not guess scope or use the first CLI host.

Fourteen boundary cases failed before implementation, followed by four paired
real-controller cases (`/tmp/r42-standalone-reconcile-red.log` and
`/tmp/r42-standalone-paired-red.log`). The pure positive count-helper regression
also failed because the operation did not exist
(`/tmp/r42-snat-counts-red.log`). The final standalone command passed all
23 checks in 77.94 seconds (`/tmp/r42-standalone-reconcile-final.log`), including
actual Ansible execution with private two-node API/rule fixtures. It covers
malformed WANT, missing/ambiguous/foreign declaration bindings, declared-state
mismatch, stale/incomplete facts, offline/wrong-host coverage, disabled source
cleanup, nonmember/unrelated preservation and no writes during WANT99 with
105 rules or after deletion. The first green attempt had two fixture assertions
wrongly expecting no rule-history file; the existing fixture initializes an
empty history file, so the corrected tests require its contents to remain `[]`.

Twelve source-count helper cases and 36 existing planner cases passed together
in 1.88 seconds (`/tmp/r42-snat-counts-green.log`). The standalone README,
parameter source and generated JSON describe the exact 0/1/99 contract; the
bundled generator passed. Three existing actual-controller default/stable
Ansible checks passed in 35.70 seconds, with 24 deselected
(`/tmp/r42-standalone-controller-dispatch-check.log`, handle64685 exit0).
Scoped Ruff, formatting and whitespace checks pass. Independent source review
found no mutation-scope issue. The count helper validates supplied verified
receipts without independently enforcing their age; this standalone flow ensures
freshness by immediately collecting them after clearing old facts. This adds a
controller action but does not expand any runtime capability marker or activate
a release. No live calls or pushes were performed.

## Delete-all read-only scope review

No deletion source was changed or disabled. `delete.all` reads the complete
cluster zone/VNet/subnet inventories, selects VNets whose `vnet_zone` equals the
requested zone, then selects their subnets using `subnet_vnet`. It deletes those
subnets, then VNets, then the zone, using the IDs returned by the reads. Selection
has no deployment ownership test: every matching object is in destructive scope.

It requests one global SDN apply after any selected object was present, then
calls legacy primary-node reconciliation with want0 for selected subnets that
have a CIDR field. Global apply can replay hooks outside the deleted zone, so
existing descriptor claims that nothing outside the zone is read/touched are
incorrect. Missing CIDRs are skipped; a later empty-inventory retry cannot
reconstruct orphan rule scope. The bundle does not enumerate/detach guest NICs,
verify pending-change scope, retain pre-delete node/source coverage, or provide
cluster-wide restoration. This review does not establish an API guarantee that
attached guests prevent deletion.

With the newer controller, its declaration deletions can already happen before
unproven apply is refused. A safe continuation must preserve the intended zone
removal semantics while establishing complete pre-write scope/ownership intent,
node membership, pending-change review, guest-attachment policy, all-node reload
proof, and exact non-target preservation. No deletion redesign or live acceptance
was performed here.
