"""Deny-list primitives (security.py) — fail-closed on injection-bearing values."""
import pytest

from r42topo.core.security import (
    document_freetext_violations,
    nested_violations,
    reject_injection,
    violates_denylist,
)


@pytest.mark.parametrize(
    "value",
    [
        "{{ malicious }}",
        "{% if x %}",
        "${IFS}",
        "a`whoami`",
        "a;rm -rf /",
        "a|b",
        "a&b",
        "line1\nline2",
        "../../etc/passwd",
        "-oProxyCommand=evil",  # leading dash → argv-flag injection
    ],
)
def test_violates_denylist_true(value):
    assert violates_denylist(value) is True


@pytest.mark.parametrize("value", ["wazuh", "192.168.140.0/24", "admin_role", "v1.0.0", ""])
def test_violates_denylist_false(value):
    assert violates_denylist(value) is False


def test_reject_injection_raises_and_passes_through():
    assert reject_injection("clean") == "clean"
    with pytest.raises(ValueError, match="forbidden"):
        reject_injection("{{ x }}")


def test_nested_violations_finds_paths():
    obj = {
        "cores": 2,
        "cmd": "a;b",
        "nested": {"ok": "fine", "bad": "${x}"},
        "list": ["clean", "{{x}}"],
    }
    paths = nested_violations(obj)
    assert "cmd" in paths
    assert "nested.bad" in paths
    assert "list[1]" in paths
    assert len(paths) == 3


def test_nested_violations_clean_is_empty():
    assert nested_violations({"cores": 2, "memory": 2048, "name": "wazuh"}) == []


def test_nested_violations_flags_bad_key():
    paths = nested_violations({"a;b": "clean"})
    assert any("(key)" in p for p in paths)


# --- canonical document free-text scan (Phase 6) ---------------------------

def test_document_freetext_violations_flags_config_and_vars():
    doc = {
        "kind": "gamenet", "name": "x",
        "defaults": {"clean": "ok", "bad": "${x}"},
        "nodes": [
            {"id": "n1", "kind": "vm", "config": {"cmd": "a;b", "cores": 2},
             "attachments": [{"vars": {"k": "{{ evil }}"}}]},
            {"id": "grp", "kind": "group",
             "children": [{"id": "c1", "kind": "vm", "config": {"x": "a|b"}}]},
        ],
    }
    paths = document_freetext_violations(doc)
    assert "defaults.bad" in paths
    assert "nodes[n1].config.cmd" in paths
    assert "nodes[n1].attachments[0].vars.k" in paths
    assert "nodes[grp].children[c1].config.x" in paths
    assert len(paths) == 4


def test_document_freetext_violations_exempts_template_fields():
    # *_template fields legitimately contain {{ }} and must NOT be flagged
    doc = {
        "kind": "gamenet", "name": "x",
        "nodes": [
            {"id": "net", "kind": "network",
             "cidr_template": "192.168.{{ bridge_base + team_id }}.0/24",
             "bridge_template": "vmbr{{ bridge_base + team_id }}",
             "networks": [{"node_ref": "net", "ip_template": "10.0.{{ team_id }}.5"}]},
        ],
        "flags": [{"id": "f", "scope": "per_team", "value_template": "{{ team_id }}"}],
    }
    assert document_freetext_violations(doc) == []


def test_document_freetext_violations_clean_topology():
    doc = {
        "kind": "gamenet", "name": "x",
        "nodes": [{"id": "n", "kind": "vm", "config": {"cores": 2, "memory": 2048}}],
    }
    assert document_freetext_violations(doc) == []
