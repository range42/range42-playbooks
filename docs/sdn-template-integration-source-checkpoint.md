# Matched SDN and isolated-template source integration

This inactive candidate combines playbooks
`1346b84ace05715c2b068f8ff10625b3122d7a16` (selected-VNet/all-NIC deletion)
with `5de4c927ecf8338ef3336342bebfcd3d54c435d6` (isolated template readiness).
The paired controller is `eecc37c7ca6785b3548468748c8153e8546d2461`, merging
`3cd79707776e7ec310b1495bf926bd076fc2c706` with
`d4d74ed4b2170c88eeec1e5571f467a972517048`.

Both read-only `git merge-tree --write-tree` checks were conflict-free before
creating separate worktrees. The resulting staged source trees exactly matched
the predictions: playbooks `3ddbd40e1f88e0a06a8c23becdfa6de21064e882` and
controller `a8b4bfeec6f1a0e4a5db630db42cff6d57262a0a` (before this documentation).
No conflict resolution or implementation rewrite was needed. The SDN task bytes
remain identical to `1346b84`; isolated-template task/helper bytes remain
identical to `5de4c927`.

Playbooks retain Hyde's separate SDN ancestor
`0b784f1cec3457ea89613f1406d2b015b32f495f`; controller retains
`c1713569d2396ea91b2e55fe1348d402613254a6`. The merge bases were the previously
accepted playbooks `a150867` and controller `99fd63c`. All original checkpoint
trees and installed runtime pins remain unchanged. No push, PVE/guest call,
shared installation or runtime-profile activation was performed.

## Matched local evidence

Checks used the backend virtual environment's Python/Ansible, with
`RANGE42_CONTROLLER_TEST_ROOT` explicitly set to
`/tmp/r42-sdn-template-controller-integration-20260911` for playbook tests.

- Controller: **102 passed in 32.57s**, exit0, handle31842. Files:
  `test_owned_vm_create.py`, `test_sdn_delete_scope.py`, `test_sdn_delete_role.py`,
  `test_snat_cluster.py`, `test_snat_source_counts.py`.
  Log: `/tmp/r42-sdn-template-integration-controller.log`.
- Isolated template: **89 passed in 190.03s**, exit0, handle78399. All three
  `test_isolated_template_contract.py`, `test_template_ready.py` and
  `test_isolated_template_ansible.py` files ran against the merged controller.
  Log: `/tmp/r42-sdn-template-integration-template.log`.
- Paired SDN: **18 passed in 247.55s**, exit0, handle71286. Covers actual
  controller/Ansible stable and verified-apply preservation, authoritative zone
  POST membership and quorum refusal, standalone 99 counts and 0/1 policy,
  missing-rule refusal, all-NIC selected deletion/preview/foreign-zone refusal,
  whole-zone deletion/repeat, list/direct bootstrap and omitted gateway behavior.
  Log: `/tmp/r42-sdn-template-integration-sdn.log`.
- Seven selected descriptors generated with exit0 and **no generated-byte
  changes**: SDN apply/bootstrap/bootstrap.sdn_vnet/reconcile.snat_rules/
  delete.all/delete.selected and template.build.ubuntu_noble. Generator:
  `bundles/_tools/generate-bundle-params.py`; `CATALOG` pointed to the exact local
  archived catalog `7f40f5c`. Log:
  `/tmp/r42-sdn-template-integration-descriptors.log`.
- `check-callsites.py` scanned the merged scenario tree through the explicit
  `/tmp/r42-sdn-template-callsite-root-20260911` root. It reports one advisory:
  both current direct-bootstrap callers supply the optional gateway/SNAT fields.
  Those fields intentionally remain optional; omitted-gateway behavior passed
  the matched tests. The checker does not use a failing exit status for advice.
  Log: `/tmp/r42-sdn-template-integration-callsites.log`.
- Scoped Ruff and staged/working diff checks passed. Test output retains the
  existing pytest-asyncio default-loop-scope deprecation warning.

## Explicit remaining boundaries

This source integration is not a runtime acceptance or activation gate. In
particular, a separate review found that successful `cloud-init clean` alone
does not prove removal of the builder's SSH authorization. That cleanup and its
controller config/seed readback are a pending, separately tested follow-up to
this exact `5de4c927` template checkpoint. Do not resume a live build based on
these matched tests alone.

The isolated builder is an explicit operator `isolated.yml` entrypoint. The
existing template `main.yml` and descriptor still describe the historical
family builder; no UI/catalog isolated-template consumer is advertised here.

Selected deletion retains the legacy adapter's explicit `net*` convention and
now understands all concrete v3 NICs. Generated UI scenarios commonly use
`r42*` names and do not include that adapter or its inventory/vault context.
Generic UI network teardown remains a separate integration. Automatic recovery
after partial deletion remains unimplemented; retained journals require reviewed
operator recovery. Complete cluster coverage, existing legacy-iptables mutation
support limits and coordination with external/manual writers remain unchanged.

A later matched dependency release must explicitly package these source pins,
recompute/review its runtime fingerprint, bind the persistent cluster journal
and perform separately authorized acceptance. The frozen API/UI/catalog rollout
is independent of this candidate.
