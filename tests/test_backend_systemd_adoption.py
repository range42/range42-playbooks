"""Offline adoption must preserve old data and never run both API owners."""

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys

import pytest

FILES = (
    Path(__file__).resolve().parents[1]
    / "bundles/admin/software.install.deployer_api_backend/files"
)


def adoption():
    path = FILES / "container_systemd.py"
    assert path.is_file(), "Explicit systemd adoption is not implemented"
    sys.path.insert(0, str(FILES))
    try:
        spec = importlib.util.spec_from_file_location("container_systemd", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(FILES))


@pytest.mark.parametrize(
    "drift", [None, "process", "config_sha256", "environment_sha256"]
)
def test_failed_stop_recovery_verifies_full_running_identity(monkeypatch, drift):
    module = adoption()
    service = module.SystemdCLI("range42-backend-api.service", {})
    proof = {
        "process": {"pid": 42, "start_time": "100", "boot_id": "original"},
        "config_sha256": "a" * 64,
        "environment_sha256": "b" * 64,
        "enabled": "enabled",
    }
    current = {**proof, "enabled": "disabled"}
    if drift:
        current[drift] = (
            {**proof[drift], "start_time": "101"} if drift == "process" else "c" * 64
        )
    commands = []
    monkeypatch.setattr(
        service, "properties", lambda: {"ActiveState": "active", "MainPID": "42"}
    )
    monkeypatch.setattr(service, "snapshot", lambda: current)
    monkeypatch.setattr(service, "command", lambda *args: commands.append(args))
    if drift:
        with pytest.raises(ValueError, match="identity"):
            service.recover_stop(proof)
        assert commands == []
    else:
        service.recover_stop(proof)
        assert commands == [("enable", service.unit)]


@pytest.fixture
def legacy(tmp_path):
    from test_backend_container_consumer import consumer

    apply = consumer()
    config = {
        "root": str(tmp_path / "managed"),
        "name": "adopt-test",
        "image": "sha256:" + "a" * 64,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "state_dir": str(tmp_path / "state"),
        "secrets_dir": str(tmp_path / "secrets"),
    }
    plan = apply.validate_config(config)
    state = Path(plan["state_dir"])
    workspace = Path(plan["workspace_host"])
    workspace.mkdir(parents=True, mode=0o700)
    state.chmod(0o700)
    apply.provision_credentials(
        Path(plan["secrets_dir"]),
        Path(plan["database_host"]),
        uid=plan["uid"],
        gid=plan["gid"],
    )
    with sqlite3.connect(plan["database_host"]) as db:
        db.execute("CREATE TABLE original(value TEXT)")
        db.execute("INSERT INTO original VALUES ('preserved')")
    Path(plan["database_host"]).chmod(0o600)
    (workspace / "history.jsonl").write_text("original runner history\n")
    return apply, config, plan


def test_proof_rejects_changed_credentials_before_stopping(legacy):
    module = adoption()
    apply, raw, plan = legacy
    proof = {
        "version": 1,
        "unit": "range42-backend-api.service",
        "credentials": apply.credentials(plan),
        "process": {"pid": 100, "start_time": "123", "boot_id": "test"},
        "config_sha256": "b" * 64,
        "environment_sha256": "c" * 64,
        "enabled": "enabled",
    }
    (Path(plan["secrets_dir"]) / "api-token").write_text("changed-" + "x" * 40)
    with pytest.raises(ValueError, match="credential"):
        module.validate_adoption_proof(plan, proof)
    assert not Path(plan["root"]).exists()


@pytest.mark.parametrize(
    "key,value",
    [
        ("RANGE42_API_PRINCIPALS_FILE", "/private/actors.json"),
        ("RANGE42_AUDIT_ENABLED", "true"),
        ("RANGE42_GIT_SECRET_DIR", "/private/git"),
        ("RANGE42_GIT_ALLOW_HTTP", "true"),
    ],
)
def test_unmapped_existing_policy_is_refused(legacy, key, value):
    module = adoption()
    _, _, plan = legacy
    env = module.compose_document(plan, "test")["services"]["api"]["environment"]
    env[key] = value
    with pytest.raises(ValueError, match="policy|configuration"):
        module.validate_environment(plan, env)


def test_explicit_inventory_path_and_original_secrets_are_checked(legacy):
    module = adoption()
    _, _, plan = legacy
    env = module.compose_document(plan, "test")["services"]["api"]["environment"]
    env.update(
        {
            "RANGE42_API_TOKEN_FILE": plan["secrets_dir"] + "/api-token",
            "RANGE42_CREDENTIAL_KEY_FILE": plan["secrets_dir"] + "/credential-key",
        }
    )
    env.pop("RANGE42_MAINTENANCE_LOCK_FILE")
    module.validate_environment(plan, env)
    env["RANGE42_WORKSPACE_ROOT"] = "/different/workspace"
    with pytest.raises(ValueError, match="binding|configuration"):
        module.validate_environment(plan, env)


@pytest.mark.parametrize(
    "key,value",
    [
        ("API_BACKEND_INVENTORY_DIR", "/var/lib/range42/inventory"),
        ("RANGE42_BUNDLE_DIR", "/runtime/bundles"),
        ("RANGE42_WORKSPACE_TEMPLATE_DIR", "/private/template"),
    ],
)
def test_omitted_existing_optional_configuration_is_refused(legacy, key, value):
    module = adoption()
    _, _, plan = legacy
    env = module.compose_document(plan, "test")["services"]["api"]["environment"]
    env.pop("RANGE42_MAINTENANCE_LOCK_FILE")
    env.update(
        {
            "RANGE42_API_TOKEN_FILE": plan["secrets_dir"] + "/api-token",
            "RANGE42_CREDENTIAL_KEY_FILE": plan["secrets_dir"] + "/credential-key",
            key: value,
        }
    )
    with pytest.raises(ValueError, match="configuration|binding"):
        module.validate_environment(plan, env)


@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "candidate_failed",
        "stop_failed",
        "stopped_then_failed",
        "busy",
        "post_stop_busy",
        "wrong_key",
        "silent_data_change",
        "commit_failed",
        "candidate_stop_failed",
        "original_offline_failed",
    ],
)
def test_adoption_preserves_database_and_checks_offline_boundary(
    legacy, monkeypatch, mode
):
    module = adoption()
    apply, raw, plan = legacy
    events = []

    class Service:
        running = True
        enabled = "enabled"
        audits = 0
        environment = module.compose_document(plan, "test")["services"]["api"][
            "environment"
        ]

        def snapshot(self):
            return {
                "process": {"pid": 100, "start_time": "123", "boot_id": "test"},
                "config_sha256": "b" * 64,
                "environment_sha256": "c" * 64,
                "enabled": self.enabled,
            }

        def verify(self, proof):
            if mode == "wrong_key":
                raise ValueError("Original credential binding changed")

        def audit(self):
            self.audits += 1
            events.append("audit")
            if mode == "busy" or (mode == "post_stop_busy" and self.audits > 1):
                raise ValueError("Installed state is busy")

        def stop(self):
            events.append("stop-old")
            if mode == "stop_failed":
                raise ValueError("Old service stop failed")
            self.enabled = "disabled"
            self.running = False
            if mode == "stopped_then_failed":
                raise ValueError("Stop acknowledgement failed")

        def assert_stopped(self):
            assert not self.running

        def restore(self, enabled):
            events.append("restore-old")
            assert not docker.running
            self.running = True
            self.enabled = enabled

        def ready(self):
            assert self.running
            assert not docker.running
            return True

        def prepare_restore(self, proof):
            assert not docker.running
            if mode == "original_offline_failed":
                raise ValueError("Original offline readiness failed")
            with sqlite3.connect(plan["database_host"]) as db:
                assert (
                    db.execute("SELECT value FROM original").fetchone()[0]
                    == "preserved"
                )

        def recover_stop(self, proof):
            self.restore(proof["enabled"])

    service = Service()

    class Docker:
        running = False

        def _run(self, args, **kwargs):
            if args[0] == "start":
                assert not service.running
                assert (Path(plan["state_dir"]) / "maintenance.lock").read_bytes()
                events.append("start-new")
                self.running = True
                if mode in (
                    "candidate_failed",
                    "silent_data_change",
                    "candidate_stop_failed",
                ):
                    with sqlite3.connect(plan["database_host"]) as db:
                        db.execute("UPDATE original SET value='bad'")
            return ""

        def inspect(self, identifier):
            return {
                "State": {"Running": self.running},
                "Image": plan["image"],
                "Config": {},
                "HostConfig": {},
                "Mounts": [],
            }

        def stop(self, identifier):
            events.append("stop-new")
            if mode == "candidate_stop_failed":
                raise ValueError("Candidate stop failed")
            self.running = False

    docker = Docker()
    proof = {
        "version": 1,
        "unit": "range42-backend-api.service",
        "credentials": apply.credentials(plan),
        **service.snapshot(),
    }
    monkeypatch.setattr(module, "verify_image_protocol", lambda *args: plan["image"])
    monkeypatch.setattr(module, "create_candidate", lambda *args: "d" * 64)
    monkeypatch.setattr(module, "wait_health", lambda *args: None)

    def ready(*args):
        if mode in (
            "candidate_failed",
            "candidate_stop_failed",
            "original_offline_failed",
        ):
            raise ValueError("Candidate validation failed")

    monkeypatch.setattr(module, "verify_ready", ready)
    monkeypatch.setattr(module, "request", lambda *args, **kwargs: {"ready": True})
    original_write = module.write_json

    def fail_committed_record(path, value):
        original_write(path, value)
        if path.name == "installation.json":
            raise ValueError("Commit acknowledgement failed")

    if mode == "commit_failed":
        monkeypatch.setattr(module, "write_json", fail_committed_record)
    if mode == "success":
        result = module.adopt(raw, proof, docker=docker, service=service)
        assert result == {"status": "adopted", "changed": True}
        assert docker.running and not service.running and service.enabled == "disabled"
        record = json.loads((Path(plan["root"]) / "installation.json").read_text())
        assert record["credentials"] == proof["credentials"]
        assert record["container_id"] == "d" * 64
    else:
        with pytest.raises(ValueError):
            module.adopt(raw, proof, docker=docker, service=service)
        if mode in ("candidate_stop_failed", "original_offline_failed"):
            assert not service.running
            assert docker.running == (mode == "candidate_stop_failed")
            assert (Path(plan["state_dir"]) / "maintenance.lock").read_bytes()
            assert (Path(plan["root"]) / "pending.json").is_file()
            return
        assert service.running
        assert not docker.running
        if mode in ("busy", "wrong_key"):
            assert "stop-old" not in events
        if mode == "candidate_failed":
            assert events.index("stop-new") < events.index("restore-old")
        if mode == "commit_failed":
            assert not (Path(plan["root"]) / "installation.json").exists()
    with sqlite3.connect(plan["database_host"]) as db:
        assert db.execute("SELECT value FROM original").fetchone()[0] == "preserved"
    assert (
        Path(plan["workspace_host"]) / "history.jsonl"
    ).read_text() == "original runner history\n"
    assert apply.credentials(plan) == proof["credentials"]
