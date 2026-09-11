# Guarded selected-VNet deletion: source checkpoint

This continuation starts from playbooks
`0af749d14864a11b914dea1ddd5ad7ee728ec26b`, preserving its reviewed Hyde SDN
integration. The paired controller starts from `da3f540` and is checkpointed as
`3cd79707776e7ec310b1495bf926bd076fc2c706`. Original checkpoint worktrees and main
repositories were not changed; no push, shared installation or live PVE operation
was performed.

The existing `blank_scenario_2_sdn.delete_networks.sh` now runs a small Ansible
adapter. It keeps the original selected-network intent: VM/template manifest
`net*` bridge names select the objects, and the configured shared zone remains.
The adapter uses the same inventory/vault and `range42_sdn_zone` setup contract.
It no longer infers subnet CIDRs from IP octets or subnet identifiers, relies on
partial VM-ID lists, or calls unguarded deletion/reconciliation devkits.

`sdn_network.delete.selected` and `delete.all` use one shared guarded task flow.
The selected wrapper passes explicit names, preserves the zone in the expected
remaining-inventory hash, and omits only its zone removal request. Whole-zone
behavior remains the default of `delete.all`. Both normal paths require complete
privileged pending/guest inspection, same API/SSH cluster identity, original
all-node snapshots, rechecked scope, durable cluster admission, verified global
apply and exact non-target/nonmember rule preservation.

The journal retains both requested selection and authoritative existing objects.
An incomplete operation blocks another selection/zone before mutation; a
completed absent repeat performs no apply or orphan-rule cleanup. A VNet absent
from authoritative declarations supplies no guessed CIDR. Same-zone unselected
guest attachments and rules remain outside removal scope.

`--dry-run`, `--check` and `-C` invoke explicit read-only scope inspection, rather
than Ansible check mode that would skip required commands. Preview has no
journal/declaration/apply/rule writes and explicitly does not claim rule-snapshot
or mutation-admission proof. Its current observations cannot authorize a later
write.

## Focused evidence

The initial checkpoint used the existing backend virtual environment's Python/Ansible,
with `RANGE42_CONTROLLER_TEST_ROOT` pointing at the isolated paired controller.

- **52 controller scope cases passed** in 2.33s, including the original guards
  and ten selected-scope cases. Nine new cases failed against the old unfiltered
  planner before implementation. Log: `/tmp/r42-sdn-selected-scope-green.log`.
- **Five actual collector/Ansible role cases passed** in 11.60s, checking selected
  input forwarding and positive/negative API/SSH cluster identity pairing.
  Log: `/tmp/r42-sdn-selected-role-green.log` (session7263).
- **23 paired playbooks/CLI cases passed** in 181.63s, actual pytest exit0.
  Log: `/tmp/r42-sdn-selected-matched.log` (session68012). These cover the original
  nine whole-zone cases, nine selected mutation/preview/refusal/partial cases,
  three read-only flag forms, shell argument/failure propagation and the actual
  legacy CLI→Ansible→guarded-bundle consumer. They retain local API/iptables
  boundary fixtures; no live mutation is implied.
- The positive selected run removes only its subnet and VNet, leaves the zone
  and same-zone neighbour/guest intact, restores unrelated rule identity/order,
  preserves target-source copies on nonmembers, and repeats without writes.
  Refusals cover missing CIDRs, pending declarations, attached guests, offline or
  wrongly mapped nodes and post-snapshot scope drift. Partial failure preserves
  journal bytes and blocks a changed selection before any further write.
- Both bundle descriptors generate successfully. Shell syntax, scoped Ruff and
  diff checks pass. Final formatting of seven owned Python files preserved
  identical ASTs to the tested source.

The additional-NIC continuation starts from playbooks `c233f141` and retains
controller `3cd79707776e7ec310b1495bf926bd076fc2c706` unchanged. Its real
CLI→Ansible boundary suite reproduced **16 failures** against the old adapter:
the secondary bridge was omitted and malformed/contradictory input reached the
deletion bundle. All **18 boundary cases then passed**, including legacy v1/v2
VM/template compatibility. Logs: `/tmp/r42-selected-nics-red.log` and
`/tmp/r42-selected-nics-green.log`.

These checks use local `python3 -m pytest` and its sibling `ansible-playbook`.
`tests/test_sdn_delete_manifest_nics.py` also invokes the real selected bundle
and paired controller with disposable API/iptables transport fixtures. The
fixture includes primary and additional NIC VNets, an attached same-zone
neighbour, an attached guest in a separate zone, and NAT copies on a nonmember
node. No live network or guest operation is implied.

The final affected run passed **27 cases in 123.46s**, actual pytest exit0
(session49287; `/tmp/r42-selected-nics-final.log`): 18 manifest boundary cases,
three paired CLI deletion/preview/foreign-secondary-NIC cases, five existing CLI
cases and one whole-zone deletion/repeat case. The deletion receipt contains
only both selected subnets and VNets; exact zone lists and unrelated/nonmember
rule identities, multiplicities and order remain unchanged. Preview and foreign
selection have no declaration/apply/rule writes or deletion journal record.
Scoped Ruff, shell syntax, YAML parsing and diff checks pass. The only emitted
test warning is the environment's existing pytest-asyncio default-loop-scope
deprecation. Independent source review found no blocker.

Reproduce the affected run from the playbooks tree with the matching controller:

```sh
RANGE42_CONTROLLER_TEST_ROOT=/tmp/r42-sdn-selected-delete-controller-next-wave \
  python3 -m pytest -q tests/test_sdn_delete_manifest_nics.py \
  tests/test_sdn_delete_selected_cli.py \
  tests/test_sdn_delete_all.py::test_delete_removes_zone_then_cleans_members_and_preserves_every_other_rule
```

## Remaining operational limits

Automatic recovery/resume/rollback after partial deletion is not implemented.
The private journal retains attempted versus acknowledged operations for an
operator-reviewed recovery. External/manual SDN, guest NIC and rule writers
still require coordination; this is not an atomic cluster transaction. Existing
legacy-iptables-only mutation support and collector/journal bounds remain.
The additional-NIC continuation retains legacy version 1/2 top-level `bridge`
selection and supports the actual concrete version 3 `nics[].bridge` layout.
It validates contiguous integer indexes and exact top-level management bridge/IP
agreement before selecting all explicit `net*` bridges. Version 3 template
references do not grant network ownership. Unsupported/mixed versions and
malformed or contradictory layouts refuse before entering the guarded bundle.

This matches `range42-deployer-ui/src/services/concreteScenario.js`'s emitted
VM manifest and the NIC layout in
`range42-backend-api/app/core/scenario_manifest.py`; it does not infer bridges
from UI draft `network_id` values, executable extra-config strings or addresses.
Generated UI scenarios do not include this legacy CLI/layout or automatically
provide its inventory/vault context. Their common `r42*` names remain outside
the legacy `net*` selection convention. Generic generated-scenario network
deletion therefore remains a separate integration boundary.

No release activation or live selected-delete acceptance is claimed. A reviewed
matched controller/playbooks release and stable per-cluster state configuration
are prerequisites. Earlier 47-guest read-only collector results remain scoped to
their exact prior source bytes.
