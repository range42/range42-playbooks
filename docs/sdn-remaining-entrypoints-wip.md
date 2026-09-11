# Remaining SDN entrypoints — partial checkpoint, do not activate

The user requested a checkpoint because usage was nearly exhausted. This work
starts from playbooks `c5c9567f217b316c6ccc5ba04ae0cbf0e223318d`, paired with
controller `92e68c91f63cba64ad304d2e2c3f750320db6c16`. No controller, installer,
live VM, network, firewall, release, or provider state was changed in this slice.
No source was pushed.

## Work currently present

The direct-parameter `bootstrap.sdn_vnet` entrypoint is a thin input-validation
adapter into the existing cluster bootstrap composite. It requires integer
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

The next implementation should give both wrappers one shared bootstrap task
body with a private, explicit input mapping, or otherwise prove that unrelated
ambient bundle inputs cannot override the adapter's declared parameters. Do not
work around it by setting a global `BUNDLE_SDN_VNETS` fact that can contaminate
later calls. The original standalone entrypoint source is retained by Git at
the base commit. This WIP has not been activated.

Scoped Ruff and whitespace checks pass. No broader suite or new test sweep was
started after the pause request. Parameter descriptions/generated metadata,
paired real-controller preservation tests for this adapter and final source
review remain unfinished. Treat this as partial source work, not a deployable
matched release.

## Standalone reconciliation remains unimplemented

`reconcile.snat_rules/main.yml` is unchanged and still calls the legacy
primary-node action. Parent-approved next contract:

- Explicit desired states 0/1 require one authoritative CIDR-to-VNet-to-zone
  binding, a complete current cluster snapshot, and the existing guarded
  reconciliation path. Missing or ambiguous bindings must fail before rules
  change. Preserve external/nonmember rules and stable no-apply semantics.
- Existing debug scenarios use `WANT=99` as a counter, including after a subnet
  is deleted. Preserve this compatibility only as explicitly read-only all-node
  snapshot/count output. The old operation can actually delete rules when the
  live count exceeds 99, so it must not remain a disguised mutation path.
- Debug `07d-attach_second_card.yml` requests `WANT=0` after raw subnet/VNet/zone
  deletion. Fresh authoritative binding is then unavailable. Orphan cleanup
  needs a retained, reviewed pre-delete membership contract; do not guess its
  scope or silently use the first CLI host. This remains deletion work.

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
