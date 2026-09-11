"""Golden images must not retain the temporary builder's SSH authorization."""

import base64
import hashlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

HELPER = (
    Path(__file__).resolve().parents[1]
    / "bundles/proxmox/template.build.ubuntu_noble/files/template_ready.py"
)
BLOB = b"\0\0\0\x0bssh-ed25519\0\0\0\x20" + bytes(range(32))
KEY = b"ssh-ed25519 " + base64.b64encode(BLOB)
OTHER = b"ssh-ed25519 " + base64.b64encode(BLOB[:-1] + b"\xff")
FINGERPRINT = hashlib.sha256(BLOB).hexdigest()


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location(
        "template_ready_authorization", HELPER
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_key_removal_preserves_other_authorizations_comments_and_line_endings(
    helper,
):
    unrelated = b"# keep\r\n" + OTHER + b" unrelated\r\n"
    owned = b'command="echo \\"quoted\\"; exit 1",no-pty ' + KEY + b" owned\n"
    cleaned, count = helper.without_builder_key(
        unrelated + owned + KEY + b"\n", FINGERPRINT
    )
    assert cleaned == unrelated
    assert count == 2


def test_key_text_inside_another_keys_command_or_comment_does_not_remove_it(helper):
    data = b'command="echo ' + KEY + b'" ' + OTHER + b" # " + KEY + b"\n"
    assert helper.without_builder_key(data, FINGERPRINT) == (data, 0)


@pytest.mark.parametrize(
    "data",
    [b'command="unterminated ' + KEY, KEY + b"\0", b"\xff active-key", b"x" * 65537],
)
def test_malformed_or_unbounded_authorization_refuses_before_mutation(helper, data):
    with pytest.raises(ValueError):
        helper.without_builder_key(data, FINGERPRINT)


def prepare(helper, monkeypatch, root):
    files = []
    for username, home in [("alice", "/home/alice"), ("root", "/root")]:
        directory = root / home.lstrip("/") / ".ssh"
        directory.mkdir(parents=True, mode=0o700)
        path = directory / "authorized_keys"
        path.write_bytes(OTHER + b" preserved\n" + KEY + b" builder\n")
        path.chmod(0o640)
        files.append(path)
    monkeypatch.setattr(
        helper.pwd,
        "getpwnam",
        lambda name: SimpleNamespace(
            pw_dir="/root" if name == "root" else "/home/alice",
            pw_uid=os.getuid(),
            pw_gid=os.getgid(),
        ),
    )
    monkeypatch.setattr(
        helper,
        "command",
        lambda *_args: (
            0,
            b"authorizedkeysfile .ssh/authorized_keys .ssh/authorized_keys2\nauthorizedkeyscommand none\n",
        ),
    )
    return files


def test_owned_user_and_root_keys_removed_atomically_per_file_with_permissions_preserved(
    helper, monkeypatch, tmp_path
):
    files = prepare(helper, monkeypatch, tmp_path)
    plan = helper.authorization_plan(
        "alice", FINGERPRINT, time.monotonic() + 5, tmp_path
    )
    assert helper.remove_authorizations(plan, FINGERPRINT)
    for path in files:
        assert path.read_bytes() == OTHER + b" preserved\n"
        assert path.stat().st_mode & 0o777 == 0o640
        assert path.stat().st_uid == os.getuid()


@pytest.mark.parametrize(
    "problem", ["missing_key", "symlink", "hardlink", "custom_path", "external_command"]
)
def test_ambiguous_or_unsupported_layout_is_rejected_before_any_key_change(
    helper, monkeypatch, tmp_path, problem
):
    files = prepare(helper, monkeypatch, tmp_path)
    if problem == "missing_key":
        files[1].write_bytes(OTHER + b"\n")
    elif problem == "symlink":
        files[1].rename(files[1].with_name("target"))
        files[1].symlink_to("target")
    elif problem == "hardlink":
        os.link(files[1], files[1].with_name("linked"))
    else:
        output = (
            b"authorizedkeysfile /etc/ssh/keys\nauthorizedkeyscommand none\n"
            if problem == "custom_path"
            else b"authorizedkeysfile .ssh/authorized_keys\nauthorizedkeyscommand /usr/bin/custom\n"
        )
        monkeypatch.setattr(helper, "command", lambda *_args: (0, output))
    before = files[0].read_bytes()
    with pytest.raises((ValueError, OSError)):
        helper.authorization_plan("alice", FINGERPRINT, time.monotonic() + 5, tmp_path)
    assert files[0].read_bytes() == before


@pytest.mark.parametrize("change", ["edited", "appeared"])
def test_changed_authorization_after_validation_prevents_any_mutation(
    helper, monkeypatch, tmp_path, change
):
    files = prepare(helper, monkeypatch, tmp_path)
    plan = helper.authorization_plan(
        "alice", FINGERPRINT, time.monotonic() + 5, tmp_path
    )
    before = files[0].read_bytes()
    if change == "edited":
        files[1].write_bytes(files[1].read_bytes() + b"# concurrent change\n")
    else:
        files[1].with_name("authorized_keys2").write_bytes(KEY + b"\n")
    with pytest.raises(ValueError):
        helper.remove_authorizations(plan, FINGERPRINT)
    assert files[0].read_bytes() == before


def test_interrupted_multifile_removal_never_claims_completion(
    helper, monkeypatch, tmp_path
):
    files = prepare(helper, monkeypatch, tmp_path)
    plan = helper.authorization_plan(
        "alice", FINGERPRINT, time.monotonic() + 5, tmp_path
    )
    original_replace = helper.os.replace
    calls = []

    def replace(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise OSError("simulated interruption")
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(helper.os, "replace", replace)
    with pytest.raises(OSError):
        helper.remove_authorizations(plan, FINGERPRINT)
    assert files[0].read_bytes() == OTHER + b" preserved\n"
    assert KEY in files[1].read_bytes()
    assert not list(tmp_path.rglob(".range42-clean-*"))


@pytest.mark.parametrize(
    "problem", [None, "clean_failed", "clean_changed_authorization"]
)
def test_same_guest_cleanup_requires_identity_reset_then_exact_authorization_removal(
    helper, monkeypatch, tmp_path, problem
):
    files = prepare(helper, monkeypatch, tmp_path)
    expected = {"build_id": "a" * 32, "plan_sha256": "b" * 64}
    identity = tmp_path / "etc/machine-id"
    identity.parent.mkdir()
    identity.write_text("original-machine-id")
    instance = tmp_path / "var/lib/cloud/instance"
    instance.mkdir(parents=True)
    monkeypatch.setattr(helper, "observe", lambda *_args: {"verified": True})
    events = []

    def command(argv, *_args):
        events.append(argv[0])
        if argv[0] == "/usr/sbin/sshd":
            return (
                0,
                b"authorizedkeysfile .ssh/authorized_keys .ssh/authorized_keys2\nauthorizedkeyscommand none\n",
            )
        assert argv == ["cloud-init", "clean", "--machine-id"]
        if problem == "clean_failed":
            return 1, b"private failed hook"
        identity.write_text("uninitialized\n")
        instance.rmdir()
        if problem == "clean_changed_authorization":
            files[1].write_bytes(files[1].read_bytes() + b"# changed\n")
        return 0, b"private hook output"

    monkeypatch.setattr(helper, "command", command)
    result = helper.clean_identity(
        expected,
        time.monotonic() + 30,
        tmp_path,
        ssh_user="alice",
        key_sha256=FINGERPRINT,
    )
    if problem:
        assert result is None
        assert KEY in files[0].read_bytes()
    else:
        assert result == {
            "version": 1,
            **expected,
            "clone_identity": "reset",
            "builder_authorization": "removed",
            "builder_key_sha256": FINGERPRINT,
        }
        assert all(KEY not in path.read_bytes() for path in files)
    assert events == ["/usr/sbin/sshd", "/usr/sbin/sshd", "cloud-init"]
