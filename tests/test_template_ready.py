"""A halted or partly configured guest must never become a successful template."""

import importlib.util
import json
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
USER_DEPRECATION = (
    "'user' of type string is deprecated in 22.2 and scheduled to be removed in "
    "27.2. Use 'users' list instead."
)


def compatibility_status():
    # Exact shape/count/return code observed in the owned Noble build. Only the
    # public documented deprecation is retained; no private guest data is used.
    return {
        **STATUS,
        "extended_status": "degraded done",
        "recoverable_errors": {"DEPRECATED": [USER_DEPRECATION] * 2},
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
        "cloud_init_warning_category": "none",
        "cloud_init_warning_count": 0,
    }


def test_exact_scalar_user_deprecation_preserves_package_success_and_warning_proof(
    helper,
):
    proof = helper.readiness(
        compatibility_status(), 2, EXPECTED, EXPECTED, 0, b"", True
    )
    assert proof is not None
    assert proof["cloud_init_warning_category"] == "proxmox_scalar_user_deprecation"
    assert proof["cloud_init_warning_count"] == 2
    assert proof["package_audit"] == "clean"
    assert USER_DEPRECATION not in json.dumps(proof)


@pytest.mark.parametrize(
    "changes",
    [
        {"marker": {**EXPECTED, "build_id": "c" * 32}},
        {"audit_rc": 1},
        {"audit_output": b"private unfinished package"},
        {"package_semaphore": False},
    ],
)
def test_compatibility_keeps_current_owner_package_audit_and_semaphore_required(
    helper, changes
):
    args = {
        "status": compatibility_status(),
        "status_rc": 2,
        "marker": EXPECTED,
        "expected": EXPECTED,
        "audit_rc": 0,
        "audit_output": b"",
        "package_semaphore": True,
        **changes,
    }
    assert helper.readiness(**args) is None


def test_recognized_final_stage_warnings_must_also_exist_in_aggregate(helper):
    status = compatibility_status()
    status["modules-final"] = {
        **STATUS["modules-final"],
        "recoverable_errors": {"DEPRECATED": [USER_DEPRECATION] * 2},
    }
    assert (
        helper.readiness(status, 2, EXPECTED, EXPECTED, 0, b"", True)[
            "cloud_init_warning_count"
        ]
        == 2
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"recoverable_errors": {"DEPRECATED": [USER_DEPRECATION, "unknown warning"]}},
        {"recoverable_errors": {"WARNING": [USER_DEPRECATION]}},
        {"recoverable_errors": {"DEPRECATED": [USER_DEPRECATION + " private text"]}},
        {"recoverable_errors": {"DEPRECATED": []}},
        {"recoverable_errors": {"DEPRECATED": [USER_DEPRECATION] * 33}},
        {"recoverable_errors": {"DEPRECATED": [None]}},
        {"recoverable_errors": []},
        {"extended_status": "done"},
        {"errors": ["package failure"]},
        {
            "modules-final": {
                **STATUS["modules-final"],
                "recoverable_errors": {"WARNING": ["package failure"]},
            }
        },
        {
            "modules-final": {
                **STATUS["modules-final"],
                "recoverable_errors": {"DEPRECATED": [USER_DEPRECATION] * 3},
            }
        },
    ],
)
def test_known_deprecation_never_masks_other_or_inconsistent_outcomes(helper, changes):
    assert (
        helper.readiness(
            {**compatibility_status(), **changes}, 2, EXPECTED, EXPECTED, 0, b"", True
        )
        is None
    )


def prepare_observation(helper, monkeypatch, tmp_path, status, rc):
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps(EXPECTED))
    semaphore = tmp_path / "semaphore"
    semaphore.touch()
    paths = {
        "/var/lib/range42-template-build.json": marker,
        "/var/lib/cloud/instance/sem/config_package_update_upgrade_install": semaphore,
    }
    monkeypatch.setattr(helper, "Path", lambda path: paths[path])
    calls = []

    def command(argv, *_args):
        calls.append(argv)
        return (
            (rc, json.dumps(status).encode()) if argv[0] == "cloud-init" else (0, b"")
        )

    monkeypatch.setattr(helper, "command", command)
    return calls


def test_observe_allows_known_rc2_to_reach_real_readiness_and_audit(
    helper, monkeypatch, tmp_path
):
    calls = prepare_observation(
        helper, monkeypatch, tmp_path, compatibility_status(), 2
    )
    proof = helper.observe(EXPECTED, time.monotonic() + 5)
    assert proof is not None
    assert proof["cloud_init_warning_count"] == 2
    assert calls == [["cloud-init", "status", "--format=json"], ["dpkg", "--audit"]]


@pytest.mark.parametrize(
    "status,rc",
    [
        (
            {
                **STATUS,
                "recoverable_errors": {"WARNING": ["private warning"]},
                "extended_status": "degraded done",
            },
            2,
        ),
        ({**STATUS, "status": "error", "errors": ["private failure"]}, 1),
        (STATUS, 7),
    ],
)
def test_terminal_unsupported_status_fails_without_spending_remaining_wait(
    helper, monkeypatch, tmp_path, status, rc, capsys
):
    calls = prepare_observation(helper, monkeypatch, tmp_path, status, rc)
    monkeypatch.setattr(
        "sys.argv",
        [
            "template_ready.py",
            "--build-id",
            EXPECTED["build_id"],
            "--plan-sha256",
            EXPECTED["plan_sha256"],
        ],
    )

    def no_sleep(_seconds):
        pytest.fail("A terminal incompatible outcome must not repeat the1800s wait")

    monkeypatch.setattr(helper.time, "sleep", no_sleep)
    assert helper.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result == {"template_readiness": "unsupported_cloud_init_completion"}
    assert calls == [["cloud-init", "status", "--format=json"]]


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
