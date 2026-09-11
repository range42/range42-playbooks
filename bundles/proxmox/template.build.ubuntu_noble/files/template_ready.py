#!/usr/bin/env python3
"""Wait for a current owned template's successful upgrade; print fixed proof only."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import selectors
import shlex
import signal
import stat
import subprocess
import time
import uuid


USER_DEPRECATION = (
    "'user' of type string is deprecated in 22.2 and scheduled to be removed in "
    "27.2. Use 'users' list instead."
)


class ReadinessRejected(RuntimeError):
    """A fixed public reason for a terminal outcome that cannot become ready."""


def without_builder_key(data, fingerprint):
    """Remove exact key blobs, preserving every other line byte-for-byte."""
    if (
        len(data) > 65536
        or b"\0" in data
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    ):
        raise ValueError("unsupported_authorization")
    lines = data.splitlines(keepends=True)
    if len(lines) > 1024:
        raise ValueError("unsupported_authorization")
    output, removed = [], 0
    for line in lines:
        if not line.strip() or line.lstrip().startswith(b"#"):
            output.append(line)
            continue
        try:
            fields = shlex.split(line.decode("utf-8"), comments=False)
            position = next(
                (
                    i
                    for i in range(min(2, len(fields)))
                    if re.fullmatch(r"(?:ssh-|ecdsa-|sk-)[A-Za-z0-9@._+-]+", fields[i])
                ),
                None,
            )
            if position is None or len(fields) <= position + 1:
                raise ValueError("unsupported_authorization")
            blob = base64.b64decode(fields[position + 1], validate=True)
            if not blob:
                raise ValueError("unsupported_authorization")
        except (UnicodeError, ValueError) as error:
            raise ValueError("unsupported_authorization") from error
        if hashlib.sha256(blob).hexdigest() == fingerprint:
            removed += 1
        else:
            output.append(line)
    return b"".join(output), removed


def keyfile_parent(path, root):
    parts = path.relative_to(root).parts
    if not parts or any(part in (".", "..") for part in parts):
        raise ValueError("unsupported_authorization_path")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            following = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = following
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_keyfile(path, root, uid):
    directory = keyfile_parent(path, root)
    try:
        parent = os.fstat(directory)
        if parent.st_mode & 0o022 or parent.st_uid not in (0, uid):
            raise ValueError("unsafe_authorization_directory")
        parent_identity = (parent.st_dev, parent.st_ino)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            return None, None, parent_identity
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size > 65536
                or info.st_uid not in (0, uid)
                or info.st_mode & 0o022
            ):
                raise ValueError("unsafe_authorization_file")
            data = stream.read(65537)
            if len(data) > 65536:
                raise ValueError("unsafe_authorization_file")
            identity = (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
                info.st_uid,
                info.st_gid,
                stat.S_IMODE(info.st_mode),
            )
            return data, identity, parent_identity
    finally:
        os.close(directory)


def authorization_plan(username, fingerprint, deadline, root=Path("/")):
    """Validate both cloud-init credential destinations before cleaning anything."""
    if (
        not isinstance(username, str)
        or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username)
        or not isinstance(fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    ):
        raise ValueError("invalid_builder_authorization")
    plan = []
    for account in dict.fromkeys((username, "root")):
        entry = pwd.getpwnam(account)
        home = Path(entry.pw_dir)
        if not home.is_absolute() or ".." in home.parts:
            raise ValueError("unsupported_authorization_path")
        left = deadline - time.monotonic()
        if left <= 0:
            raise ValueError("authorization_verification_unavailable")
        effective = command(
            [
                "/usr/sbin/sshd",
                "-T",
                "-C",
                f"user={account},host=localhost,addr=127.0.0.1",
            ],
            min(3, left),
            32768,
        )
        if effective is None or effective[0] != 0:
            raise ValueError("authorization_verification_unavailable")
        settings = {}
        for line in effective[1].decode("utf-8").splitlines():
            key, _, value = line.partition(" ")
            if key in ("authorizedkeysfile", "authorizedkeyscommand"):
                if key in settings:
                    raise ValueError("unsupported_authorization_layout")
                settings[key] = value
        supported = {".ssh/authorized_keys", ".ssh/authorized_keys2"}
        paths = settings.get("authorizedkeysfile", "").split()
        if (
            not paths
            or not set(paths) <= supported
            or settings.get("authorizedkeyscommand") != "none"
        ):
            raise ValueError("unsupported_authorization_layout")
        count = 0
        for name in ("authorized_keys", "authorized_keys2"):
            path = root / home.relative_to("/") / ".ssh" / name
            snapshot = read_keyfile(path, root, entry.pw_uid)
            data = snapshot[0]
            cleaned, removed = (
                without_builder_key(data, fingerprint)
                if data is not None
                else (None, 0)
            )
            count += removed
            plan.append(
                {
                    "path": path,
                    "root": root,
                    "uid": entry.pw_uid,
                    "snapshot": snapshot,
                    "cleaned": cleaned,
                    "removed": removed,
                }
            )
        if count == 0:
            raise ValueError("builder_authorization_not_found")
    return plan


def remove_authorizations(plan, fingerprint):
    # Validate every snapshot before the first write, including missing files.
    for item in plan:
        if read_keyfile(item["path"], item["root"], item["uid"]) != item["snapshot"]:
            raise ValueError("authorization_changed")
    for item in plan:
        if not item["removed"]:
            continue
        path, root, snapshot = item["path"], item["root"], item["snapshot"]
        directory = keyfile_parent(path, root)
        temporary = ".range42-clean-" + uuid.uuid4().hex
        try:
            info = os.fstat(directory)
            if (info.st_dev, info.st_ino) != snapshot[2] or read_keyfile(
                path, root, item["uid"]
            ) != snapshot:
                raise ValueError("authorization_changed")
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            with os.fdopen(fd, "wb") as stream:
                os.fchown(stream.fileno(), snapshot[1][5], snapshot[1][6])
                os.fchmod(stream.fileno(), snapshot[1][7])
                stream.write(item["cleaned"])
                stream.flush()
                os.fsync(stream.fileno())
            if read_keyfile(path, root, item["uid"]) != snapshot:
                raise ValueError("authorization_changed")
            os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)
    for item in plan:
        current, _, parent = read_keyfile(item["path"], item["root"], item["uid"])
        if (
            current != item["cleaned"]
            or parent != item["snapshot"][2]
            or (current is not None and without_builder_key(current, fingerprint)[1])
        ):
            raise ValueError("authorization_removal_not_verified")
    return True


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


def clean_identity(
    expected, deadline, root=Path("/"), *, ssh_user=None, key_sha256=None
):
    if not observe(expected, deadline):
        return None
    try:
        authorizations = authorization_plan(ssh_user, key_sha256, deadline, root)
    except (OSError, ValueError, KeyError):
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
        if time.monotonic() >= deadline or not remove_authorizations(
            authorizations, key_sha256
        ):
            return None
        return {
            "version": 1,
            **expected,
            "clone_identity": "reset",
            "builder_authorization": "removed",
            "builder_key_sha256": key_sha256,
        }
    except (OSError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--wait-seconds", type=int, default=1800)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--ssh-user")
    parser.add_argument("--ssh-key-sha256")
    args = parser.parse_args()
    if (
        not re.fullmatch(r"[0-9a-f]{32}", args.build_id)
        or not re.fullmatch(r"[0-9a-f]{64}", args.plan_sha256)
        or not 1 <= args.wait_seconds <= 1800
        or (
            args.clean
            and (
                not args.ssh_user
                or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", args.ssh_user)
                or not args.ssh_key_sha256
                or not re.fullmatch(r"[0-9a-f]{64}", args.ssh_key_sha256)
            )
        )
    ):
        print('{"template_readiness":"invalid_request"}')
        return 1
    expected = {"build_id": args.build_id, "plan_sha256": args.plan_sha256}
    try:
        if args.clean:
            proof = clean_identity(
                expected,
                time.monotonic() + 30,
                ssh_user=args.ssh_user,
                key_sha256=args.ssh_key_sha256,
            )
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
