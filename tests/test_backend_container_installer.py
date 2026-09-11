"""Test installer state preservation with disposable files and no live hosts."""
from __future__ import annotations

import base64
import importlib.util
import os
from pathlib import Path
import stat

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bundles/admin/software.install.deployer_api_backend/files/container_install.py"


def helper():
    assert HELPER.is_file(), "installer needs validated, repeatable secret provisioning"
    spec = importlib.util.spec_from_file_location("container_install", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_credentials_are_private_valid_and_never_rotated(tmp_path):
    directory = tmp_path / "secrets"
    database = tmp_path / "state.db"
    module = helper()
    module.provision_credentials(directory, database, uid=os.getuid(), gid=os.getgid())
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    assert len(before["api-token"].strip()) >= 32
    assert len(base64.urlsafe_b64decode(before["credential-key"].strip())) == 32
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir())
    database.write_text("an existing database")
    module.provision_credentials(directory, database, uid=os.getuid(), gid=os.getgid())
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize("existing", [None, "api-token", "credential-key"])
def test_existing_database_with_missing_credentials_never_gets_a_new_key(tmp_path, existing):
    directory = tmp_path / "secrets"
    database = tmp_path / "state.db"
    database.write_text("must be preserved")
    if existing:
        directory.mkdir(mode=0o700)
        value = "a" * 64 if existing == "api-token" else base64.urlsafe_b64encode(b"x" * 32).decode()
        (directory / existing).write_text(value)
        (directory / existing).chmod(0o600)
    before = {path.name: path.read_bytes() for path in directory.iterdir()} if directory.exists() else {}
    with pytest.raises(ValueError, match="original.*credentials"):
        helper().provision_credentials(directory, database, uid=os.getuid(), gid=os.getgid())
    after = {path.name: path.read_bytes() for path in directory.iterdir()} if directory.exists() else {}
    assert before == after
    assert database.read_text() == "must be preserved"


@pytest.mark.parametrize("filename", ["api-token", "credential-key"])
def test_malformed_existing_credentials_are_not_logged_replaced_or_partially_initialized(tmp_path, filename):
    directory = tmp_path / "secrets"
    directory.mkdir(mode=0o700)
    value = "bad-secret-must-not-be-echoed"
    (directory / filename).write_text(value)
    with pytest.raises(ValueError) as error:
        helper().provision_credentials(directory, tmp_path / "db", uid=os.getuid(), gid=os.getgid())
    assert value not in str(error.value)
    assert list(directory.iterdir()) == [directory / filename]
    assert (directory / filename).read_text() == value


def test_secret_symlink_cannot_read_or_replace_another_file(tmp_path):
    directory = tmp_path / "secrets"
    directory.mkdir(mode=0o700)
    unrelated = tmp_path / "unrelated"
    unrelated.write_text("protected")
    (directory / "api-token").symlink_to(unrelated)
    with pytest.raises(ValueError, match="regular|symbolic"):
        helper().provision_credentials(directory, tmp_path / "db", uid=os.getuid(), gid=os.getgid())
    assert unrelated.read_text() == "protected"
    assert (directory / "api-token").is_symlink()
    assert not (directory / "credential-key").exists()
