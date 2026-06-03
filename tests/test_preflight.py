"""Preflight sync/no-IO subset parity (ported from range42-backend-api
``tests/core/test_preflight.py`` + ``test_preflight_topology.py``
@ feature/gamenet-authoring-v1, issue #67).

Only the pure, synchronous, no-I/O checks are ported into r42topo.core:
``check_vmids``, ``check_resource_budget``, ``check_secret_completeness``,
``check_topology_node_role``, ``check_vmid_safety_for_topology`` plus the
``PreflightCheck`` / ``PreflightReport`` value types. The backend's
filesystem check (``check_topology_assets``), the ``httpx`` network checks,
and the ``run_declarative_checks`` dispatcher are impure and stay in the
backend / future r42runtime — their tests are intentionally not mirrored.

Note: ``check_vmid_safety_for_topology`` was ``async`` in the backend purely
for call-site symmetry with the network checks (it performs no I/O). With
those checks deferred, the r42topo port is plain synchronous.
"""
from r42topo.core.preflight import (
    PreflightReport,
    check_resource_budget,
    check_secret_completeness,
    check_topology_node_role,
    check_vmid_safety_for_topology,
    check_vmids,
)


# --- check_vmids -----------------------------------------------------------

def test_vmids_block_on_protected():
    r = check_vmids([100, 200], host_overrides=None)
    assert r.result == "block"
    assert "protected" in r.detail.lower()


def test_vmids_block_on_duplicate():
    r = check_vmids([200, 200], host_overrides=None)
    assert r.result == "block"


def test_vmids_pass_on_clean_set():
    r = check_vmids([200, 201, 202], host_overrides=None)
    assert r.result == "pass"


# --- check_resource_budget -------------------------------------------------

def test_resource_budget_warn_at_95_pct():
    r = check_resource_budget(total_ram_mb_required=95000, host_total_ram_mb=100000)
    assert r.result == "warn"


def test_resource_budget_block_over_110():
    r = check_resource_budget(total_ram_mb_required=112000, host_total_ram_mb=100000)
    assert r.result == "block"


def test_resource_budget_block_on_zero_capacity():
    r = check_resource_budget(total_ram_mb_required=100, host_total_ram_mb=0)
    assert r.result == "block"


def test_resource_budget_pass_under_90():
    r = check_resource_budget(total_ram_mb_required=50000, host_total_ram_mb=100000)
    assert r.result == "pass"


# --- check_secret_completeness ---------------------------------------------

def test_secret_completeness_detects_missing():
    env = [{"name": "admin_password", "secret": True, "required": True}]
    r = check_secret_completeness(env, provided={})
    assert r.result == "block"
    r = check_secret_completeness(env, provided={"admin_password": "x"})
    assert r.result == "pass"


def test_secret_completeness_ignores_non_secret():
    env = [{"name": "some_var", "secret": False, "required": True}]
    r = check_secret_completeness(env, provided={})
    assert r.result == "pass"


# --- PreflightReport aggregation -------------------------------------------

def test_report_aggregates_block_over_warn():
    rep = PreflightReport()
    rep.checks.append(check_resource_budget(total_ram_mb_required=95000, host_total_ram_mb=100000))  # warn
    rep.checks.append(check_vmids([100], host_overrides=None))  # block
    assert rep.result == "block"


def test_report_aggregates_warn_when_no_block():
    rep = PreflightReport()
    rep.checks.append(check_resource_budget(total_ram_mb_required=95000, host_total_ram_mb=100000))  # warn
    rep.checks.append(check_vmids([200], host_overrides=None))  # pass
    assert rep.result == "warn"


def test_report_pass_when_all_pass():
    rep = PreflightReport()
    rep.checks.append(check_vmids([200], host_overrides=None))
    rep.checks.append(check_resource_budget(total_ram_mb_required=10, host_total_ram_mb=1000))
    assert rep.result == "pass"


# --- check_vmid_safety_for_topology ----------------------------------------

def test_vmid_safety_blocks_protected_vmids():
    """Topology that computes a VMID into the protected range must block."""
    topology = {
        "nodes": [
            {"id": "vm-bad", "kind": "vm", "role": "admin",
             "replication": {"scope": "shared"},
             "template_vmid": 9001, "vmid_base": 100},  # 100 is protected
        ]
    }
    check = check_vmid_safety_for_topology(topology, team_count=1, host_overrides=None)
    assert check.result == "block"
    assert "protected" in check.detail.lower() or "100" in check.detail


def test_vmid_safety_blocks_duplicate_vmids():
    """Two per-team VMs whose computed VMIDs collide must block."""
    # team_count=2, vms_per_team=2:
    # node-a (base=5000) team 1 seq 0 → 5000 + 1*2 + 0 = 5002
    # node-b (base=4999) team 1 seq 1 → 4999 + 1*2 + 1 = 5002  (collides)
    topology = {
        "nodes": [
            {"id": "vm-a", "kind": "vm", "role": "trainee",
             "replication": {"scope": "per_team"}, "vmid_base": 5000},
            {"id": "vm-b", "kind": "vm", "role": "trainee",
             "replication": {"scope": "per_team"}, "vmid_base": 4999},
        ]
    }
    check = check_vmid_safety_for_topology(topology, team_count=2, host_overrides=None)
    assert check.result == "block"
    assert "duplicate" in check.detail.lower()


def test_vmid_safety_passes_for_safe_topology():
    """Safe topology with shared and per-team VMs at vmid_base=5000 → pass."""
    topology = {
        "nodes": [
            {"id": "vm-shared", "kind": "vm", "role": "admin",
             "replication": {"scope": "shared"}, "vmid_base": 5000},
            {"id": "vm-team-a", "kind": "vm", "role": "trainee",
             "replication": {"scope": "per_team"}, "vmid_base": 5100},
            {"id": "vm-team-b", "kind": "lxc", "role": "trainee",
             "replication": {"scope": "per_team"}, "vmid_base": 5200},
        ]
    }
    check = check_vmid_safety_for_topology(topology, team_count=2, host_overrides=None)
    assert check.result == "pass", f"expected pass, got {check.result}: {check.detail}"


# --- check_topology_node_role ----------------------------------------------

def test_check_topology_node_role_blocks_missing_role():
    """A VM node without a 'role' field must produce a block check."""
    topology = {
        "nodes": [
            {"id": "vm-noop", "kind": "vm", "replication": {"scope": "shared"}},
        ]
    }
    checks = check_topology_node_role(topology)
    blocks = [c for c in checks if c.result == "block"]
    assert blocks, "expected at least one block for missing role"
    assert any(c.code == "TOPOLOGY_NODE_MISSING_ROLE" for c in blocks)


def test_check_topology_node_role_passes_when_all_have_roles():
    """Every VM/LXC node has a role → exactly one pass check."""
    topology = {
        "nodes": [
            {"id": "vm-a", "kind": "vm", "role": "admin", "replication": {"scope": "shared"}},
            {"id": "lxc-b", "kind": "lxc", "role": "trainee", "replication": {"scope": "per_team"}},
        ]
    }
    checks = check_topology_node_role(topology)
    assert len(checks) == 1
    assert checks[0].result == "pass"


def test_check_topology_node_role_ignores_non_vm_nodes():
    """Networks, routers, etc. without 'role' do not block — only vm/lxc require it."""
    topology = {
        "nodes": [
            {"id": "net-a", "kind": "network"},
            {"id": "rt-a", "kind": "router"},
            {"id": "vm-a", "kind": "vm", "role": "admin", "replication": {"scope": "shared"}},
        ]
    }
    checks = check_topology_node_role(topology)
    assert all(c.result == "pass" for c in checks)
    assert len(checks) == 1
