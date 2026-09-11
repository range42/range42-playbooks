# Guarded zone deletion — source checkpoint, not activated

This slice starts from playbooks 38110a9/controller 2f35a76. Read-only remote checks
on 2026-09-11 found Hyde's separate `feat-sdn-implementation` branches unchanged:
playbooks `0b784f1cec3457ea89613f1406d2b015b32f495f`, controller
`c1713569d2396ea91b2e55fe1348d402613254a6`. No implicit merge/rebase, guest/network change, installer update, activation or
push was performed. The root subsequently ran the bounded read-only collector
trial documented below; no mutation was performed.

The explicit deletion semantics remain all subnets and VNets belonging to one
zone, then that zone. The implementation adds complete pre-write scope and guest
checks, private durable evidence and the existing all-node apply/reconcile/
restoration pipeline. It does not introduce a separate rule-mutation mechanism.
See the bundle README for the required stable state setting and exact bounds.

The matching deletion controller source is checkpointed at
`765f228e55323bd387b3fc9eaa5a0cff8b334d37`, including the canonical-order fix.
Its helper SHA256 is
`a7bcb8f51aa64bf77c269ce39cc811152e1cdd7b0224b2e2e81fd1270ed9e898`.
The journal primitives are checkpointed in controller 0a05e63 and 43e48cd. The
latter binds version 2 records/history to the actual cluster CA, serializes
all zones under one root-wide lock, rejects incomplete/unsafe/unbound legacy
records, and matches Proxmox's zone-name grammar. It passed 59 focused tests,
including actual concurrent cross-zone admission and 265 phase events, in 9.46s.
Only the journal helper and its tests were included in those commits.

## Evidence and review findings

- Initial paired deletion regressions failed 7/7 against the old flow. The first
  fixed run finished 5 passed / 2 failed because the test wrapper did not resolve
  nested include paths. After correcting the fixture, actual handle 19737 passed
  all 7 cases in 61.32s (`/tmp/r42-delete-paired-green2.log`). No fixture guard was
  removed; subsequent cases extend this with completed repeats, incomplete
  absent-zone retry refusal, changed membership and a failed node reload.
- Initial pure scope/collector checks passed 32 cases. Review exposed missing
  canonical CIDRs outside the selected zone, which could conceal conflicting
  source ownership. Both new regressions failed before the complete inventory
  validation and now pass.
- A real child-process timeout regression showed that killing only `pvesh`
  could leave a descendant alive. The collector now kills its still-owned
  process group before reaping. The regression passed in 10.23s.
- Certificate regressions require exactly one valid root-CA SHA256 fingerprint;
  API/SSH identity must match. Pending guest removal still counts as attachment.
  Arbitrary QEMU arguments/raw LXC networking cannot establish safe detachment.
- An aggregate-output regression demonstrated that per-command limits alone
  were insufficient. The collector now caps aggregate output before retaining
  more than 16 MiB. Private raw journal records remain bounded separately.

The expanded controller command (actual handle 65380 exit 0) passed 154 tests in
33.68s: deletion scope, bounded root collector, actual role API/SSH CA matching,
private journal, existing cluster planner and read-only source counts. Log:
`/tmp/r42-delete-controller-final.log`. The expanded paired command (actual
handle 95934 exit 0) passed 9 cases in 96.32s, including successful empty-zone repeat,
incomplete absent-zone retry refusal, changed scope before writes and failed
second-node reload with no rule cleanup. Log: `/tmp/r42-delete-paired-final.log`.

Independent review then found harmless API subnet row reordering changed the
literal scope comparison. A new regression failed before canonical subnet
ordering; the affected scope suite passed 34 cases in 1.56s afterward
(`/tmp/r42-delete-order-green.log`, actual handle 6396 exit 0). The collector's reviewed
frozen hash before that ordering-only correction was
`bbf7d342614c29d6324738bed444da6bd20786132cb61680d10ea38d0b73e2ad`.
Scoped Ruff, formatting, whitespace checks and the bundled parameter generator
pass. The existing pytest asyncio configuration warning remains.

## Read-only lab compatibility trial

The root ran the frozen pre-ordering helper above against `pve01` and the
retained `r42smoke` zone on the 47-guest lab. Actual observer 87560 completed
exit 0, but the collector itself returned rc 1 after 118.26s at 13:58:26Z with
`Deletion inventory command timed out`. No scope was accepted and no declaration,
rule or guest write was performed. This is a real-target compatibility/performance
limitation, not passing deletion acceptance. The subsequent fixed-category trace confirmed cumulative startup overhead:
64 commands, first guest read at 27.166s, approximately 1.9–2.0s per QEMU read,
and the last pending request starting at 119.694s exhausted the overall 120s
budget. The lab roster was 47 QEMU guests and no LXC guests. Root trace evidence:
`/tmp/r42-sdn-delete-readonly-20260911/trace-result.json`.

Controller `1dbc75d8396d546d6718c389e17b8f423349b386` removes redundant QEMU
`/config` reads and batches
at most two independent guest reads from the main thread. LXC retains current
and pending reads, because raw reference-valued LXC fields are omitted by the
pending endpoint. WNOWAIT retains child identity through process-group cleanup;
failure or timeout stops every sibling group before children are reaped. The
existing 10s/120s and 4MiB/16MiB bounds remain unchanged, as do full attachment
checks and the final roster reread.

Ten focused regressions failed before this optimization. Actual handle67821
passed 63 collector/scope/role checks in 37.16s; actual handle76091 passed both
affected paired success/partial-retry cases in 49.50s, with 7 deselected.
Logs: `/tmp/r42-delete-batch-final.log` and `/tmp/r42-delete-batch-paired.log`.
Review follow-up `97f9f9a6e73bf6daf752e6f344f3caeed13c4758` rejects a malformed
pending row containing only `key`, while retaining legitimate delete-only rows.
That failure was reproduced before the fix; all 42 scope checks then passed
(`/tmp/r42-delete-key-only-green.log`). The final helper is frozen at SHA256
`f76b5956896de67b2b4122df2f66f742c827c81f9fca37d1b4eae40b282c95a5`.
Local results do not establish improved live performance; a reviewed repeat
read-only probe remains pending. No live deletion acceptance is claimed.


## Remaining limits

Automatic partial-delete resume and rollback are not implemented. Incomplete
journals retain original scope and phase history and block new deletion rather
than interpreting absent declarations as completed cleanup. Recovery needs
operator review of all covered nodes and pending configuration. Keep the state
root stable across CLI/backend attempts; per-attempt workspaces cannot enforce
that protection. Installers/runtime packaging have not been updated in this
slice. CA changes, copied state from another cluster and legacy unbound records
require review.

Other SDN entrypoints, guest NIC edits and external/manual writers still require
coordination. The journal only serializes `delete.all` through the same configured
cluster state root. API reads and writes are not atomic, the apply parent does
not expose child UPIDs, and no cross-node rollback is promised. Unknown schema,
unsupported zone/iptables backends, failed permissions/reads or partial reloads
must refuse or retain incomplete evidence. Matched live acceptance remains
pending; no deployment capability marker is expanded here.

## Authoritative API contracts consulted

Official sources were read on 2026-09-11; the implementation discovers optional
families and refuses unfamiliar ones rather than requiring the latest API.

- [Cluster resources](https://raw.githubusercontent.com/proxmox/pve-manager/master/PVE/API2/Cluster.pm)
  filters guests by VM.Audit.
  [RPCEnvironment permissions](https://raw.githubusercontent.com/proxmox/pve-access-control/master/src/PVE/RPCEnvironment.pm)
  grants root visibility but drops zero-effective ACL paths from the public
  permission listing. That listing cannot prove absence of hidden guests.
- [SDN core](https://raw.githubusercontent.com/proxmox/pve-network/master/src/PVE/Network/SDN.pm)
  `pending_config` merges running/editable state and retains deleted rows.
  [Zones API](https://raw.githubusercontent.com/proxmox/pve-network/master/src/PVE/API2/Network/SDN/Zones.pm)
  distinguishes `pending=1`, `running=1` and ordinary editable configuration.
  [Subnet API](https://raw.githubusercontent.com/proxmox/pve-network/master/src/PVE/API2/Network/SDN/Subnets.pm)
  loads the current parent VNet for access checks; pending deletion is refused
  before requesting that parent's subnet list.
- [Fabric API](https://raw.githubusercontent.com/proxmox/pve-network/master/src/PVE/API2/Network/SDN/Fabrics.pm),
  [prefix lists](https://raw.githubusercontent.com/proxmox/pve-network/master/src/PVE/API2/Network/SDN/PrefixLists.pm)
  and [route-map entries](https://raw.githubusercontent.com/proxmox/pve-network/master/src/PVE/API2/Network/SDN/RouteMaps.pm)
  establish the optional pending response shapes. DNS/IPAM are directory
  families but are not pending families committed by `compile_running_cfg`.
- [QEMU configuration](https://raw.githubusercontent.com/proxmox/qemu-server/master/src/PVE/API2/Qemu.pm)
  and [LXC configuration](https://raw.githubusercontent.com/proxmox/pve-container/master/src/PVE/API2/LXC.pm)
  expose `/pending` entries with current `value`, optional `pending` and delete
  flags. `/config?current=1` selects current configuration explicitly.
  [GuestHelpers `config_with_pending_array`](https://raw.githubusercontent.com/proxmox/pve-guest-common/master/src/PVE/GuestHelpers.pm)
  skips reference-valued current fields, including raw LXC arrays. A pending-only
  optimization must therefore retain separate current LXC configuration reads.
- [Certificate API](https://raw.githubusercontent.com/proxmox/pve-manager/master/PVE/API2/Certificates.pm)
  includes `pve-root-ca.pem`; [certificate parsing](https://raw.githubusercontent.com/proxmox/pve-common/master/src/PVE/Certificate.pm)
  supplies its SHA256 fingerprint. This binds API/SSH target and journal identity.
- [Bookworm zone schema](https://raw.githubusercontent.com/proxmox/pve-network/stable-bookworm/src/PVE/Network/SDN/Zones/Plugin.pm)
  and [current zone schema](https://raw.githubusercontent.com/proxmox/pve-network/master/src/PVE/Network/SDN/Zones/Plugin.pm)
  require 2–8 alphanumeric characters, beginning with a letter.
  [Bookworm SDN directory](https://raw.githubusercontent.com/proxmox/pve-network/stable-bookworm/src/PVE/API2/Network/SDN.pm)
  has the five original families and lacks newer locking; no `/sdn/lock`
  dependency was introduced.
