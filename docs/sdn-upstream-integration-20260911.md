# Hyde SDN branch integration — 2026-09-11

This source merge includes the separately maintained upstream SDN branch at
`0b784f1cec3457ea89613f1406d2b015b32f495f` and our guarded implementation at
`32995c1ca5d6eeff866a0bac192947cfb00bd498`. Fresh remote reads confirmed that
upstream head and controller head `c1713569d2396ea91b2e55fe1348d402613254a6`
remain current. The controller candidate already contains its upstream head.
No `dev` or `main` branch is changed by this integration.

## Preserved behavior

Upstream commits `5f24262`, `391429d` and `0b784f1` respectively preserve
neighboring NAT sources during an internet action, preserve existing counts
around an explicit apply, and preserve undeclared sources during bootstrap.
The five overlapping composite files retain the reviewed cluster implementation
byte-for-byte from `32995c1`. That implementation takes complete snapshots before
writes, verifies all-node apply completion, reconciles only declared targets and
restores exact unrelated rule identities, order and multiplicity, including
mixed rule shapes and nonmember nodes. Explicitly reviewed new or changed NAT
sources retain their intended changes during an apply.

The upstream on/off/toggle changes are the same 64 noncomment changed lines
after normalizing action labels. Each was compared; the bootstrap and explicit
apply changes were reviewed separately. Their preservation intent is retained
through the existing shared cluster helpers rather than duplicate count loops.

Seven focused integration cases passed in 28.02 seconds (handle37545, exit0):
internet actions leave neighboring declared policy alone, bootstrap snapshots
before writes and preserves undeclared sources, and explicit apply preserves
prior duplicates without erasing legitimate new pending NAT. These execute real
Ansible orchestration with a replaced PVE role boundary. Earlier paired controller
and deletion tests remain separate evidence; this merge does not repeat or
claim a live PVE mutation acceptance.

Reproduction:

```sh
python -m pytest -q tests/test_sdn_scoped_nat_preservation.py -k 'internet_change_does_not_reconcile or bootstrap_snapshots_before_writes or explicit_apply_preserves_prior_duplicates'
```

## Preserved upstream script and remaining boundary

`blank_scenario_2_sdn.delete_networks.sh` includes the upstream changes exactly;
`bash -n` passed. It remains a legacy scenario-selected network deletion script,
which keeps the shared zone. It is not the new guarded `delete.all` bundle and
has not received live mutation acceptance in this work.

Its complete attachment visibility, pre-write pending/snapshot checks,
retained recovery intent and cluster-wide rule preservation still need the
shared guarded pipeline. Some read failures are currently suppressed, and the
script may delete declarations before later checks or reconciliation refuse.
A future selected-VNet adapter must retain the script's scenario scope and shared
zone; replacing it with whole-zone deletion would broaden its scope incorrectly.
The source merge neither disables the script nor treats it as an accepted safe
network lifecycle. This limitation remains explicit before runtime promotion.

The shared installation stays on API f068 / UI472 / catalog0b with playbooks
a150867 and controller99fd63. The integrated playbooks and newer controller
remain source candidates. Stable deletion-journal configuration, operator recovery
and matched live SDN acceptance are still required.
