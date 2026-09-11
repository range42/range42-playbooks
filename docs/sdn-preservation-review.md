# Incomplete scoped SDN preservation checkpoint

Do not activate this branch. It starts at installed playbooks `a150867` and is
paired with the controller preservation branch in
`/tmp/r42-sdn-controller-preservation-next-wave`. The live installation still
uses playbooks `a150867` and controller `99fd63c`.

Reviewed upstream commits: `5f24262` (internet non-target preservation),
`391429d` (apply preservation) and `0b784f1` (bootstrap preservation). A blanket
replacement would remove the existing VM resource, multi-NIC and runtime
capability extensions. Their count-based restoration also conflicts with the
installed controller's strict 0/1 desired-state primitive and cannot distinguish
rules with different comments or translated source addresses.

This checkpoint instead snapshots exact rule identities before writes. Internet
on/off/toggle reconcile only the selected subnet; already matching requests skip
global apply. Bootstrap preserves undeclared sources and applies when an enabled
subnet lacks a live rule. Explicit standalone apply accepts reviewed changed
source CIDRs for pending removal/reordering/replacement and permits appended NAT
rules for new sources while removing known appended duplicates of untouched rules.

Fourteen real-Ansible orchestration cases pass; the controller's 26 helper tests
and two real-Ansible action cases also pass. Focused Ruff and whitespace checks
pass. No live SDN operation or full repository suite was run for this checkpoint.
Test logs are `/tmp/r42-sdn-preservation-green.log`,
`/tmp/r42-snat-preservation-controller-green.log` and
`/tmp/r42-snat-preservation-ansible-green.log`.

Remaining before review/activation:

- The controller continuation now closes the numbered-delete race for cooperating
  legacy xtables writers using one outer flock and private child lock file.
  Its 34 focused tests pass, including independent-process contention. nft and
  unknown backends are rejected before snapshot/table access; a safe nft path
  remains unimplemented and the lab backend is not yet verified. See the paired
  controller's `docs/snat-preservation-locking.md` for the exact boundary.
- The pending-change workflow is now implemented with
  `BUNDLE_SDN_CHANGED_SOURCES`: validate a unique canonical IPv4 CIDR list before
  apply, record the scope in a reviewed snapshot, and require the same scope at
  restoration. Non-NAT and untouched-source changes still fail closed. The
  current continuation passes 55 focused controller checks and 11 real-Ansible
  bundle orchestration checks; logs are `/tmp/r42-snat-pending-green.log` and
  `/tmp/r42-sdn-reviewed-bundle-green.log`. This is not a rollback mechanism or
  desired-state verification for the explicitly changed sources.
  A subsequent compatibility regression requires the actual reviewed snapshot
  before apply, so an older controller cannot silently ignore the review flag;
  all three final apply checks pass in `/tmp/r42-sdn-controller-capability-green.log`.
- Resolve/document multi-node coverage; snapshots cover one SSH target while
  SDN apply affects the cluster.
- Update bundle READMEs and compatibility documentation; check capability
  requirements and run full repository/integration checks on matched pins.
- Review and freeze explicit paired commits before any scoped live acceptance.

Primary references: [Proxmox SDN](https://github.com/proxmox/pve-docs/blob/master/pvesdn.adoc)
and [iptables locking and rule operations](https://man7.org/linux/man-pages/man8/iptables.8.html).
