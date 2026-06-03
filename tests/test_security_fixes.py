"""Regression tests for the ECC review findings (security + correctness)."""

import json

import pytest
from pydantic import ValidationError as PydErr

from r42playbooks.core.catalog import load_catalog
from r42playbooks.core.catalog_models import MatrixRule, NetworkPolicyTemplate, ZoneDecl
from r42playbooks.core.compiler.network_policy import compile_network_policy, lint_segmentation
from r42playbooks.core.errors import CompileError, TopologyError
from r42playbooks.core.extravars import resolve_universal_extravars
from r42playbooks.core.models import Topology


# --- C3: wildcard-source DROP must not be shadowed undetected ---

def test_linter_catches_wildcard_drop_bypass(topology_factory, fake_catalog):
    """accept ctf->admin (w200) + drop *->admin (w500) must be flagged, not pass."""
    t = Topology.model_validate(topology_factory())
    pol = load_catalog(fake_catalog).network_policies["air-gap-ctf"].model_copy(deep=True)
    pol.matrix = [
        MatrixRule(src="ctf", dst="admin", action="accept", comment="opens ctf->admin"),
        MatrixRule(src="*", dst="admin", action="drop", comment="drop all to admin"),
    ]
    compiled = compile_network_policy(t, pol, version="1.1.0")
    assert lint_segmentation(compiled, pol, t) != []  # bypass is now caught


def test_air_gap_reference_policy_still_clean(topology_factory, fake_catalog):
    """The legitimate air-gap-ctf policy must NOT trip the stricter linter."""
    t = Topology.model_validate(topology_factory())
    pol = load_catalog(fake_catalog).network_policies["air-gap-ctf"]
    compiled = compile_network_policy(t, pol, version="1.1.0")
    assert lint_segmentation(compiled, pol, t) == []


# --- C1: params / overrides injection ---

def test_attachment_params_reject_injection(topology_factory):
    spec = topology_factory()
    spec["boxes"][0]["attachments"] = [
        {"kind": "role", "catalog_ref": "software.install.x",
         "params": {"cmd": "{{ lookup('pipe','id') }}"}},
    ]
    with pytest.raises(PydErr):
        Topology.model_validate(spec)


def test_network_policy_overrides_reject_injection(topology_factory):
    spec = topology_factory()
    spec["network_policy"]["overrides"] = {"wan_interface": "eth0; iptables -F"}
    with pytest.raises(PydErr):
        Topology.model_validate(spec)


# --- C2: missing/invalid service IP must fail closed, not broaden the rule ---

def test_missing_service_ip_raises(topology_factory, fake_catalog):
    t = Topology.model_validate(topology_factory())
    pol = load_catalog(fake_catalog).network_policies["air-gap-ctf"].model_copy(deep=True)
    pol.params = {}  # remove siem_ip default
    with pytest.raises(CompileError):
        compile_network_policy(t, pol, version="1.1.0")


# --- H1/H2/H3: field guards ---

def test_description_rejects_injection(topology_factory):
    with pytest.raises(PydErr):
        Topology.model_validate(topology_factory(description="{{ evil }}"))


def test_proxmox_node_rejects_empty(topology_factory):
    with pytest.raises(PydErr):
        Topology.model_validate(topology_factory(proxmox_node=""))


def test_scenario_rejects_leading_dash(topology_factory):
    with pytest.raises(PydErr):
        Topology.model_validate(topology_factory(scenario="-evil"))


def test_schema_version_pinned(topology_factory):
    with pytest.raises(PydErr):
        Topology.model_validate(topology_factory(schema_version=2))


# --- CRITICAL(py): load_topology wraps pydantic errors as TopologyError ---

def test_load_topology_wraps_schema_error(tmp_path, valid_topology_dict):
    from r42playbooks.core.io import load_topology
    bad = dict(valid_topology_dict)
    bad["proxmox_node"] = ""  # schema-invalid but valid JSON
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(TopologyError):
        load_topology(p)
