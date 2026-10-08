"""An existing vault-password file survives adoption without secret rotation."""

import hashlib
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

import pytest

from test_backend_container_consumer import consumer
from test_backend_systemd_adoption import adoption


def vault_config(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    password = directory / "vault-password"
    password.write_bytes(b"fixture vault passphrase\n")
    password.chmod(0o600)
    return {
        "root": str(tmp_path / "installation"),
        "name": "vault-test",
        "image": "sha256:" + "a" * 64,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "secrets_dir": str(directory),
        "vault_password_host": str(password),
        "vault_password_container": "/etc/range42/secrets/vault-password",
    }


def with_credentials(tmp_path):
    apply = consumer()
    raw = vault_config(tmp_path)
    plan = apply.validate_config(raw)
    apply.provision_credentials(
        Path(plan["secrets_dir"]),
        Path(plan["database_host"]),
        uid=plan["uid"],
        gid=plan["gid"],
    )
    return apply, raw, plan


@pytest.mark.parametrize(
    "target", ["/etc/range42/secrets/vault-password", "/run/secrets/vault_password"]
)
def test_existing_vault_is_one_readonly_file_and_hashes_exact_bytes(tmp_path, target):
    apply = consumer()
    raw = vault_config(tmp_path)
    raw["vault_password_container"] = target
    password = Path(raw["vault_password_host"])
    before = password.read_bytes()
    plan = apply.validate_config(raw)
    apply.provision_credentials(
        Path(plan["secrets_dir"]),
        Path(plan["database_host"]),
        uid=plan["uid"],
        gid=plan["gid"],
    )
    service = apply.compose_document(plan, "test")["services"]["api"]
    assert service["environment"]["VAULT_PASSWORD_FILE"] == target
    assert "VAULT_PASSWORD" not in service["environment"]
    assert [row for row in service["volumes"] if row["source"] == str(password)] == [
        {
            "type": "bind",
            "source": str(password),
            "target": target,
            "read_only": True,
            "bind": {"create_host_path": False},
        }
    ]
    assert (
        apply.credentials(plan)["vault-password"] == hashlib.sha256(before).hexdigest()
    )
    assert password.read_bytes() == before
    assert before.decode().strip() not in str(service)


def test_old_no_vault_record_normalizes_and_keeps_original_credential_identity(
    tmp_path,
):
    apply, raw, _ = with_credentials(tmp_path)
    raw.pop("vault_password_host")
    raw.pop("vault_password_container")
    plan = apply.validate_config(raw)
    assert plan["vault_password_host"] == plan["vault_password_container"] == ""
    old = {
        key: value
        for key, value in plan.items()
        if key
        not in ("database_host", "vault_password_host", "vault_password_container")
    }
    assert apply.validate_config(old) == plan
    assert set(apply.credentials(old)) == {"api-token", "credential-key"}
    assert (
        "VAULT_PASSWORD_FILE"
        not in apply.compose_document(plan, "test")["services"]["api"]["environment"]
    )


@pytest.mark.parametrize("field", ["vault_password_host", "vault_password_container"])
def test_one_sided_vault_binding_is_refused(tmp_path, field):
    raw = vault_config(tmp_path)
    raw.pop(field)
    with pytest.raises(ValueError, match="[Vv]ault"):
        consumer().validate_config(raw)


@pytest.mark.parametrize(
    "target",
    [
        "/etc",
        "/run/secrets",
        "/etc/range42/secrets",
        "/tmp/vault-password",
        "/var/lib/range42/vault-password",
        "/run/secrets/api_token",
        "/run/secrets/credential_key",
        "/etc/range42/secrets/api-token",
        "/etc/range42/secrets/credential-key",
        "/run/secrets/nested/vault-password",
    ],
)
def test_vault_target_cannot_shadow_credentials_or_writable_paths(tmp_path, target):
    raw = vault_config(tmp_path)
    raw["vault_password_container"] = target
    with pytest.raises(ValueError, match="[Vv]ault"):
        consumer().validate_config(raw)


@pytest.mark.parametrize(
    "damage",
    [
        "outside",
        "symlink",
        "parent_symlink",
        "api-token",
        "credential-key",
        "public",
        "executable",
        "wrong_uid",
        "wrong_gid",
        "directory",
        "fifo",
        "hardlink",
        "empty",
        "oversized",
    ],
)
def test_vault_source_requires_confined_private_owned_regular_file(tmp_path, damage):
    raw = vault_config(tmp_path)
    path = Path(raw["vault_password_host"])
    if damage == "outside":
        replacement = tmp_path / "outside-password"
        path.rename(replacement)
        raw["vault_password_host"] = str(replacement)
    elif damage in ("symlink", "parent_symlink"):
        replacement = tmp_path / "outside-password"
        path.rename(replacement)
        if damage == "symlink":
            path.symlink_to(replacement)
        else:
            parent = path.parent / "alias"
            parent.symlink_to(tmp_path, target_is_directory=True)
            raw["vault_password_host"] = str(parent / replacement.name)
    elif damage in ("api-token", "credential-key"):
        replacement = path.with_name(damage)
        path.rename(replacement)
        raw["vault_password_host"] = str(replacement)
    elif damage in ("public", "executable"):
        path.chmod(0o644 if damage == "public" else 0o700)
    elif damage in ("wrong_uid", "wrong_gid"):
        raw["uid" if damage == "wrong_uid" else "gid"] += 1
    elif damage in ("directory", "fifo"):
        path.unlink()
        path.mkdir() if damage == "directory" else os.mkfifo(path)
    elif damage == "hardlink":
        os.link(path, path.with_name("second-link"))
    else:
        path.write_bytes(b"" if damage == "empty" else b"x" * 4097)
    with pytest.raises(ValueError, match="[Vv]ault"):
        consumer().validate_config(raw)


def test_vault_target_cannot_shadow_private_template(tmp_path):
    raw = vault_config(tmp_path)
    raw.update(
        runtime_dir=str(tmp_path / "runtime"),
        workspace_template_dir=str(tmp_path / "template"),
        workspace_template_container="/etc/range42/secrets",
    )
    with pytest.raises(ValueError, match="[Vv]ault"):
        consumer().validate_config(raw)


def test_vault_target_cannot_shadow_individually_bound_runtime_config(tmp_path):
    raw = vault_config(tmp_path)
    raw.update(
        runtime_dir=str(tmp_path / "runtime"),
        workspace_template_dir=str(tmp_path / "template"),
        runtime_config_container="/etc/range42/secrets",
        vault_password_container="/etc/range42/secrets/ansible.cfg",
    )
    with pytest.raises(ValueError, match="[Vv]ault"):
        consumer().validate_config(raw)


def test_vault_replaced_during_descriptor_read_is_refused(tmp_path, monkeypatch):
    apply, _, plan = with_credentials(tmp_path)
    password = Path(plan["vault_password_host"])
    original_read = os.read

    def replace_after_read(fd, count):
        data = original_read(fd, count)
        replacement = password.with_name("replacement")
        replacement.write_bytes(data)
        replacement.chmod(0o600)
        replacement.replace(password)
        return data

    monkeypatch.setattr(os, "read", replace_after_read)
    with pytest.raises(ValueError, match="[Vv]ault"):
        apply.credentials(plan)


def test_update_does_not_accept_rotated_vault_or_reopen_original_with_it(
    tmp_path, monkeypatch
):
    apply, _, plan = with_credentials(tmp_path)
    original_credentials = apply.credentials(plan)
    root = Path(plan["root"])
    database = Path(plan["database_host"])
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE retained(value TEXT)")
        connection.execute("INSERT INTO retained VALUES ('original')")
    database.chmod(0o600)
    release = root / "releases" / "candidate"
    release.mkdir(parents=True)
    events = []
    candidate = "c" * 64
    original = "d" * 64

    class Gate:
        def verify(self):
            pass

        def complete(self):
            events.append("opened")

    @contextmanager
    def stopped(*args, **kwargs):
        yield Gate()

    class Docker:
        def _run(self, command, **kwargs):
            events.append(command)
            if command == ["start", candidate]:
                Path(plan["vault_password_host"]).write_bytes(
                    b"rotated during update\n"
                )

        def inspect(self, identifier):
            return {
                "Image": plan["image"],
                "State": {"Running": False},
                "Config": {},
                "HostConfig": {},
                "Mounts": [],
            }

        def stop(self, identifier):
            events.append(["stop", identifier])

    monkeypatch.setattr(apply, "verify_image_protocol", lambda *args: plan["image"])
    monkeypatch.setattr(apply, "stage", lambda *args: ("candidate", release, plan))
    monkeypatch.setattr(apply, "request", lambda *args: {"ready": True})
    monkeypatch.setattr(apply, "stopped_container", stopped)
    monkeypatch.setattr(apply, "create_candidate", lambda *args: candidate)
    monkeypatch.setattr(apply, "wait_health", lambda *args: None)
    monkeypatch.setattr(apply, "verify_ready", lambda *args: None)
    with pytest.raises(ValueError, match="credential"):
        apply.managed_update(
            Docker(),
            {
                "config": plan,
                "container_id": original,
                "credentials": original_credentials,
            },
            plan,
        )
    assert ["stop", candidate] in events
    assert ["start", original] not in events
    assert "opened" not in events
    assert (root / "pending.json").exists()
    assert not (root / "installation.json").exists()


@pytest.mark.parametrize("boundary", ["managed", "adoption"])
def test_vault_byte_drift_refuses_before_any_container_or_service_action(
    tmp_path, boundary
):
    apply, _, plan = with_credentials(tmp_path)
    original = apply.credentials(plan)
    Path(plan["vault_password_host"]).write_bytes(b"replacement fixture passphrase\n")
    if boundary == "managed":

        class NoDocker:
            def inspect(self, *args):
                pytest.fail("Credential drift reached Docker")

        with pytest.raises(ValueError, match="credential"):
            apply.verify_managed(
                NoDocker(),
                {
                    "version": 1,
                    "status": "ready",
                    "config": plan,
                    "credentials": original,
                },
                plan,
            )
    else:
        proof = {
            "version": 1,
            "unit": "range42-backend-api.service",
            "credentials": original,
            "process": {"pid": 10, "start_time": "12", "boot_id": "fixture"},
            "config_sha256": "b" * 64,
            "environment_sha256": "c" * 64,
            "enabled": "enabled",
        }
        with pytest.raises(ValueError, match="credential"):
            adoption().validate_adoption_proof(plan, proof)


@pytest.mark.parametrize("change", ["host", "container", "remove", "add_to_old"])
def test_update_cannot_relocate_or_add_remove_existing_vault_binding(
    tmp_path, monkeypatch, change
):
    apply, _, plan = with_credentials(tmp_path)
    original = dict(plan)
    changed = {**plan, "image": "sha256:" + "b" * 64}
    if change == "host":
        changed["vault_password_host"] += "-other"
    elif change == "container":
        changed["vault_password_container"] = "/run/secrets/another-password"
    elif change == "remove":
        changed.update(vault_password_host="", vault_password_container="")
    else:
        original.pop("vault_password_host")
        original.pop("vault_password_container")
    monkeypatch.setattr(
        apply,
        "verify_image_protocol",
        lambda *args: pytest.fail("Binding drift reached image preparation"),
    )
    with pytest.raises(ValueError, match="relocate|binding"):
        apply.managed_update(object(), {"config": original}, changed)


@pytest.mark.parametrize(
    "mode",
    ["match", "different_host", "omitted_candidate", "omitted_legacy", "plaintext"],
)
def test_systemd_preserves_exact_existing_file_reference_only(tmp_path, mode):
    apply, raw, plan = with_credentials(tmp_path)
    module = adoption()
    env = apply.compose_document(plan, "test")["services"]["api"]["environment"]
    env.pop("RANGE42_MAINTENANCE_LOCK_FILE")
    env.update(
        RANGE42_API_TOKEN_FILE=plan["secrets_dir"] + "/api-token",
        RANGE42_CREDENTIAL_KEY_FILE=plan["secrets_dir"] + "/credential-key",
        VAULT_PASSWORD_FILE=plan["vault_password_host"],
    )
    if mode == "different_host":
        env["VAULT_PASSWORD_FILE"] += "-other"
    elif mode == "omitted_candidate":
        raw.pop("vault_password_host")
        raw.pop("vault_password_container")
        plan = apply.validate_config(raw)
    elif mode == "omitted_legacy":
        env.pop("VAULT_PASSWORD_FILE")
    elif mode == "plaintext":
        env["VAULT_PASSWORD"] = "fixture-inline-must-refuse"
    if mode == "match":
        module.validate_environment(plan, env)
    else:
        with pytest.raises(ValueError, match="configuration|binding|policy") as error:
            module.validate_environment(plan, env)
        assert raw.get("vault_password_host", "not-present") not in str(error.value)
        assert "fixture-inline" not in str(error.value)
