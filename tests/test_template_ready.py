"""A halted or partly configured guest must never become a successful template."""

import importlib.util
import os
from pathlib import Path
import time

import pytest

HELPER = (
    Path(__file__).resolve().parents[1]
    / "bundles/proxmox/template.build.ubuntu_noble/files/template_ready.py"
)
EXPECTED = {"build_id": "a" * 32, "plan_sha256": "b" * 64}
STATUS = {
    "status": "done",
    "extended_status": "done",
    "errors": [],
    "recoverable_errors": {},
    "modules-final": {
        "start": 10,
        "finished": 20,
        "errors": [],
        "recoverable_errors": {},
    },
}


@pytest.fixture
def helper():
    assert HELPER.is_file(), "Readiness must inspect success before template conversion"
    spec = importlib.util.spec_from_file_location("template_ready", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_complete_healthy_package_stage_returns_only_fixed_proof(helper):
    proof = helper.readiness(STATUS, 0, EXPECTED, EXPECTED, 0, b"", True)
    assert proof == {
        "version": 1,
        **EXPECTED,
        "cloud_init": "done",
        "package_audit": "clean",
        "package_module": "completed",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"status_rc": 2},
        {"status_rc": 1},
        {"status": {**STATUS, "status": "running"}},
        {"status": {**STATUS, "extended_status": "degraded done"}},
        {"status": {**STATUS, "errors": ["private diagnostic must not escape"]}},
        {"status": {**STATUS, "recoverable_errors": {"WARN": ["private message"]}}},
        {"status": {**STATUS, "modules-final": {"start": 10, "finished": 0}}},
        {"status": []},
        {"status": {"status": "done"}},
        {"marker": {**EXPECTED, "build_id": "c" * 32}},
        {"marker": {}},
        {"audit_rc": 1},
        {"audit_output": b"unfinished private package name"},
        {"package_semaphore": False},
    ],
)
def test_partial_unavailable_stale_or_error_evidence_cannot_succeed(helper, changes):
    args = {
        "status": STATUS,
        "status_rc": 0,
        "marker": EXPECTED,
        "expected": EXPECTED,
        "audit_rc": 0,
        "audit_output": b"",
        "package_semaphore": True,
        **changes,
    }
    assert helper.readiness(**args) is None


def test_bounded_command_does_not_export_excessive_or_timed_out_output(helper):
    assert (
        helper.command(["/usr/bin/python3", "-c", "print('private' * 10000)"], 1, 1024)
        is None
    )
    assert (
        helper.command(
            ["/usr/bin/python3", "-c", "import time;time.sleep(2)"], 0.05, 1024
        )
        is None
    )


def test_stderr_is_retained_privately_for_audit_failure_not_silently_discarded(helper):
    result = helper.command(
        ["/usr/bin/python3", "-c", "import sys;sys.stderr.write('private warning')"],
        1,
        1024,
    )
    assert result == (0, b"private warning")
    assert helper.readiness(STATUS, 0, EXPECTED, EXPECTED, *result, True) is None


def test_timeout_kills_the_unreaped_command_group_even_if_parent_has_exited(
    helper, tmp_path
):
    pidfile = tmp_path / "pid"
    program = (
        "import subprocess;from pathlib import Path;"
        "p=subprocess.Popen(['/usr/bin/python3','-c','import time;time.sleep(10)']);"
        f"Path({str(pidfile)!r}).write_text(str(p.pid))"
    )
    try:
        assert helper.command(["/usr/bin/python3", "-c", program], 0.15, 1024) is None
        pid = int(pidfile.read_text())
        time.sleep(0.03)
        stat = Path(f"/proc/{pid}/stat")
        assert not stat.exists() or stat.read_text().split(") ")[1][0] == "Z"
    finally:
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), 9)
            except ProcessLookupError:
                pass


def test_clone_cleanup_requires_success_then_resets_identity_without_exporting_output(
    helper, tmp_path, monkeypatch
):
    calls = []
    identity = tmp_path / "etc/machine-id"
    identity.parent.mkdir()
    identity.write_text("old-machine-identity")
    instance = tmp_path / "var/lib/cloud/instance"
    instance.mkdir(parents=True)
    monkeypatch.setattr(helper, "observe", lambda *_args: {"verified": True})

    def clean(argv, *_args):
        calls.append(argv)
        identity.write_text("uninitialized\n")
        instance.rmdir()
        return 0, b"private output from a custom clean hook"

    monkeypatch.setattr(helper, "command", clean)
    assert helper.clean_identity(EXPECTED, time.monotonic() + 30, tmp_path) == {
        "version": 1,
        **EXPECTED,
        "clone_identity": "reset",
    }
    assert calls == [["cloud-init", "clean", "--machine-id"]]


def test_cleanup_failure_or_unverified_upgrade_cannot_allow_conversion(
    helper, tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(helper, "observe", lambda *_args: None)
    monkeypatch.setattr(helper, "command", lambda *args: calls.append(args))
    assert helper.clean_identity(EXPECTED, time.monotonic() + 30, tmp_path) is None
    assert not calls
    monkeypatch.setattr(helper, "observe", lambda *_args: {"verified": True})
    monkeypatch.setattr(helper, "command", lambda *_args: (1, b"private failure"))
    assert helper.clean_identity(EXPECTED, time.monotonic() + 30, tmp_path) is None
