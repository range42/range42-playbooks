"""Protected-VMID guard parity (ported from range42-backend-api
``tests/core/test_vmid_guard.py`` @ feature/gamenet-authoring-v1, issue #67).

Mirrors the backend unit tests verbatim against the r42topo port so the
convergence stays behaviour-identical.
"""
import pytest

from r42topo.core.vmid_guard import (
    DEFAULT_PROTECTED_RANGES,
    VmidProtectedError,
    assert_vmid_safe,
    filter_safe_vmids,
)


def test_default_ranges_protect_100_and_101():
    with pytest.raises(VmidProtectedError) as ei:
        assert_vmid_safe(100, host_overrides=None)
    assert ei.value.details[0]["reason"].startswith("100 is in protected range")
    with pytest.raises(VmidProtectedError):
        assert_vmid_safe(101, host_overrides=None)


def test_default_ranges_reject_9000_and_1111():
    for vmid in (1000, 1023, 1111, 4000, 4004, 9000, 9999):
        with pytest.raises(VmidProtectedError):
            assert_vmid_safe(vmid, host_overrides=None)


def test_non_protected_passes():
    assert assert_vmid_safe(4010, host_overrides=None) is None
    assert assert_vmid_safe(200, host_overrides=None) is None


def test_host_override_extends_default():
    override = [[300, 305]]
    with pytest.raises(VmidProtectedError):
        assert_vmid_safe(301, host_overrides=override)
    # 100 still protected via default.
    with pytest.raises(VmidProtectedError):
        assert_vmid_safe(100, host_overrides=override)


def test_filter_safe_vmids_partitions():
    safe, blocked = filter_safe_vmids([100, 200, 201, 9000], host_overrides=None)
    assert safe == [200, 201]
    assert blocked == [100, 9000]


def test_error_is_self_describing():
    # @dataclass does not populate Exception.args; __post_init__ must, so a
    # consumer that logs str(exc) gets the vmid + range, not an empty string.
    err = VmidProtectedError(vmid=100, reason="100-101")
    assert str(err) == "VMID 100 in protected range (100-101)"


def test_default_ranges_exported():
    # Sanity: explicitly protect 100-101 per user memory (pmg01, zbx01).
    assert (100, 101) in DEFAULT_PROTECTED_RANGES
