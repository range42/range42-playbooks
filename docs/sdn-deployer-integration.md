# Deployer integration on the SDN branch

The integration branch preserves Hyde's `feat-sdn-implementation` history. It adds owned-VM bootstrap extensions (commit `3ca69ab`) and merges upstream `55dcfd5d4f8e49ace4f6e40ee034ae67a2f0f9c5` through `b1959479ecdd3a53b7db2b6a61ab95c0d48e63a3`.

`tests/test_vm_bootstrap_extensions.py` has six real Ansible/local TLS API cases using the actual controller role: unrelated existing VM rejection before mutation, CPU/memory/secondary NIC plus disk growth, shrink rejection, CD-ROM rejection, source-image rejection and explicit primary MAC preservation. Set `RANGE42_CONTROLLER_TEST_ROOT` to the matching controller checkout; its tested integration commit is `7b11ddd`.

`tests/test_sdn_internet_reconciliation.py` adds four actual Ansible bundle tests. A fixture replaces only the controller role boundary so no host network can change. All four failed on `0601d34` because only the requested subnet was reconciled; all pass after the upstream merge. They cover on/off/toggle from both initial states, preserve other subnets' individual declarations, exclude missing/empty CIDRs and exercise a nested controller loop to catch variable rebinding.

```sh
python -m pytest tests/test_vm_bootstrap_extensions.py tests/test_sdn_internet_reconciliation.py -q
```

The NAT change is deliberately host-wide: SDN apply replays every active subnet's post-up hook, so the bundles deduplicate every declared subnet after applying the requested subnet's state. This does not make arbitrary shared-subnet changes deployment-owned. A UI/API operation needs a declared target, deployment/host operation locks, pending-change checks and a report of the complete affected scope. The tests validate orchestration and target state, not real iptables behavior or guest connectivity; shared-lab smoke tests remain necessary.
