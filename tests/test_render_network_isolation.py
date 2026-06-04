"""Tests for the 05_network_isolation render stage.

Covers:
  - render_scenario emits / skips 05_network_isolation/ based on spec.network_policy
  - main.yml / main_vms_only.yml include / exclude the isolation import
  - isolation playbook targets proxmox-cli, creates + flushes R42-FORWARD
  - rules appear in weight order (ESTABLISHED before DROP)
  - compile_network_policy_from_alloc produces correct rules for air-gap-ctf
"""

import pytest

from r42playbooks.core.allocate import allocate, Allocation
from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.compiler.network_policy import (
    compile_network_policy_from_alloc,
    W_ESTABLISHED,
    W_SERVICE_ACCEPT,
    W_INTRA,
    W_AIRGAP,
    W_DEFAULT,
)
from r42playbooks.core.models import Subnet
from r42playbooks.core.render import render_scenario
from r42playbooks.core.spec import ScenarioSpec


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cat(fake_catalog):
    return load_catalog(fake_catalog)


@pytest.fixture
def rendered_with_policy(fake_catalog, valid_spec_dict, tmp_path):
    """Render with network_policy: air-gap-ctf (already set in valid_spec_dict)."""
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    catalog = load_catalog(fake_catalog)
    alloc = allocate(spec, catalog)
    root = render_scenario(alloc, spec, catalog=catalog, dest=tmp_path / "s")
    return spec, alloc, root


@pytest.fixture
def rendered_no_policy(fake_catalog, valid_spec_dict, tmp_path):
    """Render with network_policy explicitly None."""
    spec = ScenarioSpec.model_validate({**valid_spec_dict, "network_policy": None})
    catalog = load_catalog(fake_catalog)
    alloc = allocate(spec, catalog)
    root = render_scenario(alloc, spec, catalog=catalog, dest=tmp_path / "s")
    return spec, alloc, root


# ---------------------------------------------------------------------------
# no-policy cases
# ---------------------------------------------------------------------------

def test_no_policy_no_isolation_dir(rendered_no_policy):
    _, _, root = rendered_no_policy
    assert not (root / "05_network_isolation").exists()


def test_no_policy_main_yml_excludes_isolation(rendered_no_policy):
    _, _, root = rendered_no_policy
    assert "05_network_isolation" not in (root / "main.yml").read_text()


def test_no_policy_main_vms_only_excludes_isolation(rendered_no_policy):
    _, _, root = rendered_no_policy
    assert "05_network_isolation" not in (root / "main_vms_only.yml").read_text()


# ---------------------------------------------------------------------------
# with-policy: directory + main.yml wiring
# ---------------------------------------------------------------------------

def test_policy_creates_isolation_main_yml(rendered_with_policy):
    _, _, root = rendered_with_policy
    assert (root / "05_network_isolation" / "_main.yml").is_file()


def test_policy_main_yml_includes_isolation(rendered_with_policy):
    _, _, root = rendered_with_policy
    assert "- import_playbook: ./05_network_isolation/_main.yml" in (root / "main.yml").read_text()


def test_policy_main_vms_only_includes_isolation(rendered_with_policy):
    _, _, root = rendered_with_policy
    assert "- import_playbook: ./05_network_isolation/_main.yml" in (root / "main_vms_only.yml").read_text()


def test_isolation_import_after_vm_sections(rendered_with_policy):
    """Isolation import must follow all VM infrastructure section imports in main.yml."""
    _, _, root = rendered_with_policy
    main = (root / "main.yml").read_text()
    last_infra = max(
        main.rfind("_infrastructure/_main.yml"),
        main.rfind("./01_init_proxmox/_main.yml"),
    )
    isolation_pos = main.find("05_network_isolation/_main.yml")
    assert isolation_pos > last_infra


# ---------------------------------------------------------------------------
# isolation playbook content
# ---------------------------------------------------------------------------

def test_isolation_targets_proxmox_cli(rendered_with_policy):
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    assert "hosts: proxmox-cli" in text


def test_isolation_references_vault(rendered_with_policy):
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    assert "../../secrets/default_vault.yml" in text


def test_isolation_creates_r42_forward_chain(rendered_with_policy):
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    assert "chain: R42-FORWARD" in text
    assert "chain_management: true" in text


def test_isolation_flushes_r42_forward(rendered_with_policy):
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    assert "flush: true" in text


def test_isolation_hooks_into_forward(rendered_with_policy):
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    assert "chain: FORWARD" in text
    assert "jump: R42-FORWARD" in text
    assert "action: insert" in text


def test_isolation_established_rule_present(rendered_with_policy):
    _, _, root = rendered_with_policy
    assert "ESTABLISHED" in (root / "05_network_isolation" / "_main.yml").read_text()


def test_isolation_drop_rule_ctf_to_admin(rendered_with_policy):
    """air-gap-ctf: ctf (192.168.144.0/24) -> admin (192.168.142.0/24) must DROP."""
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    assert "192.168.144.0/24" in text
    assert "jump: DROP" in text


def test_isolation_terminal_default_drop(rendered_with_policy):
    """air-gap-ctf defaults to drop — terminal comment must reflect that."""
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    assert "r42: default drop" in text


def test_isolation_established_before_drops(rendered_with_policy):
    """ESTABLISHED rule (w=0) must appear earlier in the file than the first DROP task."""
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    established_pos = text.find("ESTABLISHED")
    drop_pos = text.find("jump: DROP")
    assert 0 < established_pos < drop_pos


def test_isolation_policy_id_and_version_in_header(rendered_with_policy):
    """The generated playbook header names the policy id and the highest version."""
    _, _, root = rendered_with_policy
    text = (root / "05_network_isolation" / "_main.yml").read_text()
    assert "air-gap-ctf" in text
    assert "1.1.0" in text   # fake_catalog has v1.0.0 + v1.1.0; loader picks highest


def test_isolation_is_deterministic(fake_catalog, valid_spec_dict, tmp_path):
    """Two renders of the same spec produce byte-identical isolation playbooks."""
    spec = ScenarioSpec.model_validate(valid_spec_dict)
    catalog = load_catalog(fake_catalog)
    alloc = allocate(spec, catalog)
    a = render_scenario(alloc, spec, catalog=catalog, dest=tmp_path / "a")
    b = render_scenario(alloc, spec, catalog=catalog, dest=tmp_path / "b")
    iso_a = (a / "05_network_isolation" / "_main.yml").read_bytes()
    iso_b = (b / "05_network_isolation" / "_main.yml").read_bytes()
    assert iso_a == iso_b


# ---------------------------------------------------------------------------
# compile_network_policy_from_alloc unit tests
# ---------------------------------------------------------------------------

def _bare_alloc(subnets: list[Subnet]) -> Allocation:
    """Minimal Allocation with only subnets populated."""
    return Allocation(
        scenario="test", description="", boxes=(), templates=(), subnets=tuple(subnets)
    )


_SUBNETS = [
    Subnet(name="admin", cidr="192.168.142.0/24", bridge="vmbr142", gateway="192.168.142.1"),
    Subnet(name="ctf",   cidr="192.168.144.0/24", bridge="vmbr144"),
]


def test_compile_from_alloc_rules_sorted_by_weight(cat):
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    compiled = compile_network_policy_from_alloc(_bare_alloc(_SUBNETS), policy, version=version)
    weights = [r.weight for r in compiled.rules]
    assert weights == sorted(weights)


def test_compile_from_alloc_established_first(cat):
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    compiled = compile_network_policy_from_alloc(_bare_alloc(_SUBNETS), policy, version=version)
    first = compiled.rules[0]
    assert first.ctstate == "ESTABLISHED,RELATED"
    assert first.jump == "ACCEPT"
    assert first.weight == W_ESTABLISHED


def test_compile_from_alloc_admin_to_ctf_accept(cat):
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    compiled = compile_network_policy_from_alloc(_bare_alloc(_SUBNETS), policy, version=version)
    assert any(
        r.source == "192.168.142.0/24" and r.destination == "192.168.144.0/24" and r.jump == "ACCEPT"
        for r in compiled.rules
    )


def test_compile_from_alloc_ctf_to_admin_drop(cat):
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    compiled = compile_network_policy_from_alloc(_bare_alloc(_SUBNETS), policy, version=version)
    assert any(
        r.source == "192.168.144.0/24" and r.destination == "192.168.142.0/24" and r.jump == "DROP"
        for r in compiled.rules
    )


def test_compile_from_alloc_siem_service_rules(cat):
    """ctf -> svc:siem must produce ACCEPT rules for ports 1514 + 1515."""
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    compiled = compile_network_policy_from_alloc(_bare_alloc(_SUBNETS), policy, version=version)
    siem_rules = [
        r for r in compiled.rules
        if r.destination == "192.168.142.100" and r.jump == "ACCEPT"
    ]
    assert {r.destination_port for r in siem_rules} == {"1514", "1515"}
    assert all(r.weight == W_SERVICE_ACCEPT for r in siem_rules)


def test_compile_from_alloc_airgap_ctf_wan_drop(cat):
    """air-gap: ctf bridge (vmbr144) -> wan (vmbr0) must DROP."""
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    compiled = compile_network_policy_from_alloc(
        _bare_alloc(_SUBNETS), policy, version=version, wan_interface="vmbr0"
    )
    assert any(
        r.in_interface == "vmbr144" and r.out_interface == "vmbr0"
        and r.jump == "DROP" and r.weight == W_AIRGAP
        for r in compiled.rules
    )


def test_compile_from_alloc_terminal_default_drop(cat):
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    compiled = compile_network_policy_from_alloc(_bare_alloc(_SUBNETS), policy, version=version)
    terminal = compiled.rules[-1]
    assert terminal.weight == W_DEFAULT
    assert terminal.jump == "DROP"


def test_compile_from_alloc_intra_zone_rules(cat):
    """allow_intra_zone: each resolved zone gets a same-CIDR ACCEPT rule."""
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    compiled = compile_network_policy_from_alloc(_bare_alloc(_SUBNETS), policy, version=version)
    for cidr in ("192.168.142.0/24", "192.168.144.0/24"):
        assert any(
            r.source == cidr and r.destination == cidr
            and r.jump == "ACCEPT" and r.weight == W_INTRA
            for r in compiled.rules
        )


def test_compile_from_alloc_skips_unmapped_zones(cat):
    """A policy zone with no matching subnet in the layout is silently skipped."""
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    # Only ctf subnet; admin zone has no match
    subnets = [Subnet(name="ctf", cidr="192.168.144.0/24", bridge="vmbr144")]
    compiled = compile_network_policy_from_alloc(_bare_alloc(subnets), policy, version=version)
    assert not any(r.source == "192.168.142.0/24" for r in compiled.rules)
    assert compiled.rules[-1].weight == W_DEFAULT   # terminal still present


def test_compile_from_alloc_deterministic(cat):
    """Same inputs must produce byte-identical JSON output."""
    policy = cat.network_policies["air-gap-ctf"]
    version = cat.resolved_version("network_policies", "air-gap-ctf")
    alloc = _bare_alloc(_SUBNETS)
    a = compile_network_policy_from_alloc(alloc, policy, version=version).model_dump_json()
    b = compile_network_policy_from_alloc(alloc, policy, version=version).model_dump_json()
    assert a == b
