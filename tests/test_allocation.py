"""Pure VMID allocation parity (ported from range42-backend-api
``tests/core/test_allocation.py`` @ feature/gamenet-authoring-v1, issue #67).

Only the pure ``allocate_vmids`` is ported into r42topo.core. The backend's
``allocate_vmids_locked`` (module-global ``asyncio.Lock``) and
``ssh_controlmaster_env`` (creates ``~/.ssh/range42/``) are impure and stay in
the backend / future r42runtime — their tests are intentionally not mirrored.
"""
import pytest

from r42topo.core.allocation import allocate_vmids
from r42topo.core.errors import CompileError


def test_allocate_vmids_is_contiguous_and_skips_protected():
    reserved = {100, 101, 4000, 4001}
    out = allocate_vmids(start=99, count=5, reserved=reserved, host_overrides=None)
    # Must not include any reserved or default-protected vmid.
    for v in out:
        assert v not in reserved
        assert not (100 <= v <= 101)
        assert not (4000 <= v <= 4004)
    assert len(out) == 5
    assert len(set(out)) == 5


def test_host_overrides_are_skipped():
    out = allocate_vmids(start=200, count=3, reserved=set(), host_overrides=[[200, 202]])
    for v in out:
        assert v not in {200, 201, 202}
    assert out == [203, 204, 205]


def test_exhaustion_raises():
    # r42topo raises its own hierarchy (CompileError ⊂ TopologyError), not the
    # bare RuntimeError the backend used, so consumers catch one error family.
    with pytest.raises(CompileError):
        allocate_vmids(start=99998, count=5, reserved=set(), host_overrides=None)
