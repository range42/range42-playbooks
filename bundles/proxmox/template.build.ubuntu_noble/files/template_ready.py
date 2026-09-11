#!/usr/bin/env python3
"""Wait for a current owned template's successful upgrade; print fixed proof only."""

import argparse
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time


USER_DEPRECATION = (
    "'user' of type string is deprecated in 22.2 and scheduled to be removed in "
    "27.2. Use 'users' list instead."
)


class ReadinessRejected(RuntimeError):
    """A fixed public reason for a terminal outcome that cannot become ready."""


def known_warning_count(warnings):
    if warnings == {}:
        return 0
    if type(warnings) is not dict or set(warnings) != {"DEPRECATED"}:
        return None
    entries = warnings["DEPRECATED"]
    if (
        type(entries) is not list
        or not 1 <= len(entries) <= 32
        or any(entry != USER_DEPRECATION for entry in entries)
    ):
        return None
    return len(entries)


def completed_status(status, status_rc):
    if type(status) is not dict or status.get("status") != "done":
        return None
    warnings = known_warning_count(status.get("recoverable_errors"))
    if warnings is None or status.get("errors") != []:
        return None
    expected_rc, expected_status = (2, "degraded done") if warnings else (0, "done")
    if type(status_rc) is not int or status_rc != expected_rc:
        return None
    if status.get("extended_status") != expected_status:
        return None
    final = status.get("modules-final")
    if type(final) is not dict or final.get("errors") != []:
        return None
    final_warnings = known_warning_count(final.get("recoverable_errors", {}))
    start, end = final.get("start"), final.get("finished")
    if (
        final_warnings is None
        or final_warnings > warnings
        or type(start) not in (int, float)
        or type(end) not in (int, float)
        or not 0 < start <= end
    ):
        return None
    return warnings


def readiness(
    status, status_rc, marker, expected, audit_rc, audit_output, package_semaphore
):
    warnings = completed_status(status, status_rc)
    if (
        warnings is None
        or marker != expected
        or audit_rc != 0
        or audit_output != b""
        or not package_semaphore
    ):
        return None
    return {
        "version": 1,
        **expected,
        "cloud_init": "done",
        "package_audit": "clean",
        "package_module": "completed",
        "cloud_init_warning_category": (
            "proxmox_scalar_user_deprecation" if warnings else "none"
        ),
        "cloud_init_warning_count": warnings,
    }


def command(argv, seconds, limit):
    """Bound wall time and captured bytes before any output crosses guest SSH."""
    process = None
    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline, output = time.monotonic() + seconds, bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                for key, _ in selector.select(left):
                    chunk = os.read(key.fd, min(4096, limit + 1 - len(output)))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        output.extend(chunk)
                        if len(output) > limit:
                            return None
            return process.wait(timeout=max(0.001, deadline - time.monotonic())), bytes(
                output
            )
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if process is not None:
            # Keep a timed-out group leader unreaped until signalling its group;
            # poll() would release its PID even when a child still holds stdout.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
            process.stdout.close()


def observe(expected, deadline):
    try:
        marker_file = Path("/var/lib/range42-template-build.json")
        if marker_file.is_symlink() or marker_file.stat().st_size > 4096:
            return None
        marker = json.loads(marker_file.read_bytes())
        if marker != expected:
            return None
        result = command(
            ["cloud-init", "status", "--format=json"],
            min(5, deadline - time.monotonic()),
            65536,
        )
        if result is None:
            return None
        status_rc, raw = result
        status = json.loads(raw)
        if not isinstance(status, dict):
            return None
        terminal = status.get("status") in ("done", "error", "disabled")
        if completed_status(status, status_rc) is None:
            if terminal:
                raise ReadinessRejected("unsupported_cloud_init_completion")
            return None
        left = deadline - time.monotonic()
        if left <= 0:
            return None
        audit = command(["dpkg", "--audit"], min(5, left), 8192)
        if audit is None:
            return None
        proof = readiness(
            status,
            status_rc,
            marker,
            expected,
            *audit,
            Path(
                "/var/lib/cloud/instance/sem/config_package_update_upgrade_install"
            ).is_file(),
        )
        if proof is None:
            raise ReadinessRejected("package_completion_not_verified")
        return proof
    except (OSError, ValueError, TypeError):
        return None


def clean_identity(expected, deadline, root=Path("/")):
    if not observe(expected, deadline):
        return None
    left = deadline - time.monotonic()
    if left <= 0:
        return None
    cleaned = command(["cloud-init", "clean", "--machine-id"], min(30, left), 8192)
    if cleaned is None or cleaned[0] != 0:
        return None
    try:
        identity = root / "etc/machine-id"
        instance = root / "var/lib/cloud/instance"
        if (
            identity.is_symlink()
            or identity.stat().st_size > 64
            or identity.read_bytes() != b"uninitialized\n"
            or instance.exists()
            or instance.is_symlink()
        ):
            return None
        return {"version": 1, **expected, "clone_identity": "reset"}
    except OSError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--wait-seconds", type=int, default=1800)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    if (
        not re.fullmatch(r"[0-9a-f]{32}", args.build_id)
        or not re.fullmatch(r"[0-9a-f]{64}", args.plan_sha256)
        or not 1 <= args.wait_seconds <= 1800
    ):
        print('{"template_readiness":"invalid_request"}')
        return 1
    expected = {"build_id": args.build_id, "plan_sha256": args.plan_sha256}
    try:
        if args.clean:
            proof = clean_identity(expected, time.monotonic() + 30)
            print(
                json.dumps(
                    proof or {"template_cleanup": "not_verified"}, sort_keys=True
                )
            )
            return 0 if proof else 1
        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            proof = observe(expected, deadline)
            if proof:
                print(json.dumps(proof, sort_keys=True))
                return 0
            time.sleep(max(0, min(5, deadline - time.monotonic())))
    except ReadinessRejected as error:
        print(json.dumps({"template_readiness": str(error)}, sort_keys=True))
        return 1
    print('{"template_readiness":"success_not_verified"}')
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
