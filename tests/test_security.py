"""Deny-list primitives (security.py) — fail-closed on injection-bearing values."""
import pytest

from r42topo.core.security import (
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
