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

All commands used the existing backend virtual environment's Python/Ansible,
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

## Remaining operational limits

Automatic recovery/resume/rollback after partial deletion is not implemented.
The private journal retains attempted versus acknowledged operations for an
operator-reviewed recovery. External/manual SDN, guest NIC and rule writers
still require coordination; this is not an atomic cluster transaction. Existing
legacy-iptables-only mutation support and collector/journal bounds remain.
The legacy adapter selects existing top-level `bridge` fields and does not
infer additional NIC/network ownership. A future generic manifest adapter needs
an explicit extra-NIC selection contract.

No release activation or live selected-delete acceptance is claimed. A reviewed
matched controller/playbooks release and stable per-cluster state configuration
are prerequisites. Earlier 47-guest read-only collector results remain scoped to
their exact prior source bytes.
