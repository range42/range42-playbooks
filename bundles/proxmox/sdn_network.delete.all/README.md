# sdn_network.delete.all

Delete one explicit zone and every VNet/subnet belonging to it. The declaration
order remains subnets, VNets, zone, followed by one verified global apply and
cleanup of the removed sources on their original zone members. Selection is
zone-wide; it is not restricted to objects created by one deployment.
To keep the zone and delete only explicit VNets, use
[`sdn_network.delete.selected`](../sdn_network.delete.selected/README.md). Both
wrappers reuse `_shared/sdn_delete.yml`; the all-zone default remains unchanged.

## Required inputs and installation

`BUNDLE_SDN_ZONE` is a Proxmox zone name: 2–8 alphanumeric characters starting
with a letter. `proxmox_node` and API credentials come from the scenario vault.
The controller needs complete online/quorate cluster coverage, supported simple
zone membership, and explicit `sdn_snat_node_hosts` mapping into `proxmox_cli`.
A legitimate standalone node may use the existing single-host default.

Set `RANGE42_SDN_DELETE_STATE_DIR` to an existing absolute, stable operator-owned
state directory for the target cluster, shared by every CLI/backend attempt.
It must not be group/world writable. Do not use a fresh per-attempt config or
workspace directory: retry evidence must survive the attempt. The helper creates
its private `.sdn-delete` directory with mode 0700 and records with mode 0600.
Installers and backend runner environments must pass this setting explicitly;
this source checkpoint does not modify deployed service/container configuration.
The Ansible process user owns the state directory; this is separate from the
privileged PVE SSH user.

The mapped PVE read coordinator must execute as root and match `proxmox_node`.
Its fixed-argument `pvesh get` calls establish complete visibility, including
ACL-hidden guests. The API and SSH targets must return the same SHA256
`pve-root-ca.pem` fingerprint. That identity also binds the durable journal;
reusing the directory for another cluster or replacing the CA requires review.
No credentials or whole guest configurations are written into public results.

## Checks before the first declaration write

The bundle checks for an incomplete journal before treating an absent zone as a
successful no-op. It reads every supported SDN family and every VNet's subnets,
refuses any pending changes, and requires canonical authoritative CIDRs and
unique source/VNet/zone bindings. Optional fabrics, prefix lists and route maps
are checked when advertised. Unknown families or malformed/incomplete responses
refuse the operation.

Current and pending QEMU/LXC NIC definitions are read for every guest, including
stopped guests and templates. QEMU uses its complete `/pending` response. LXC
also reads `/config?current=1`, because raw LXC arrays are omitted from the
pending endpoint. A NIC using a selected VNet, even with a pending
removal, blocks deletion. Guests are never detached automatically. Custom QEMU
arguments/raw LXC networking, malformed NIC definitions, missing guest reads or
changed guest discovery prevent a claim of complete attachment safety.

Original rule snapshots and idle reload baselines cover every cluster node.
A second privileged inventory read must match the original scope before the
journal authorizes a write. Cluster membership must match the snapshot. The
journal stores original sources, zone membership, snapshot policies and raw
private rule evidence before any declaration removal.

## Completion and retry behavior

A single cluster-wide journal lock and record scan exclude overlapping
normal `delete.all` and `delete.selected` operations, including different
selections or zones. Each API
request has a durable before/after phase record. After declaration removal, the
original saved source/node scope remains available for the existing controller
apply/reconcile/restore pipeline. Every covered node must finish its verified
networking reload before rule cleanup. Removed sources are reconciled to zero
only on original members; unrelated and nonmember rule identities/order are
preserved. Final pending/attachment inspection and an expected remaining-config
hash verify that only the selected declarations disappeared.

Only then is the journal completed. A successful repeat can observe an absent
zone without another apply or rule change. This does not infer orphan-rule
scope from an empty inventory. An incomplete journal blocks all subsequent
zone deletions in the same cluster state root, even if the declarations are
already gone. Completed records are retained and archived before later runs.

Automatic resume/rollback of a partial deletion is **not implemented**. On a
failed request, interrupted process, failed reload or failed readback, inspect
the original journal, pending declarations and every covered node. A request
may have committed without returning a response; the journal distinguishes
attempted from acknowledged operations. Do not remove/reset the evidence to
turn a retry green. Operator-managed recovery needs a reviewed retained scope.

## Bounds and remaining operational limits

One operation supports at most 64 selected VNets and 64 selected IPv4 subnets.
The private journal is limited to 16 MiB and 512 events; bounds are checked before
writes or phase publication. Inventory reads have a 120s overall deadline,
10s per command, 4 MiB per command output and 16 MiB aggregate output. Timed-out
read command groups are killed and owned children reaped. Guest reads are
batched at most two at a time from the main thread; a failing sibling stops
both groups. The controller supports legacy
iptables; nft remains refused.

Reads and remote writes are not an atomic cluster transaction. All other SDN
writers, guest NIC changes and manual/external reloads still require operator
coordination. The journal serializes both guarded deletion entrypoints using that root. Runtime host/workspace
locks and the all-node reload guards remain necessary. Failure after a write
can leave partial state requiring inspection; no cross-node rollback is promised.

This is tested source in paired private Ansible fixtures. It has not been
activated or accepted on a live Proxmox cluster. Matching immutable controller
and playbooks dependencies, including the shared deletion task files and stable
state setting, are required before a future reviewed release.
