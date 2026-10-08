"""Opt-in real API/SQLite/Docker adoption; only systemctl transport is simulated.

Run with RANGE42_INSTALLER_MAINTENANCE_TEST_IMAGE set to an immutable local image.
No host service, remote provider, guest or runtime checkout is modified.
"""

import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time

import pytest

from test_backend_systemd_adoption import adoption

API = Path("/home/ppa/projects/range42-base/range42-backend-api")
PYTHON = API / ".venv/bin/python"
IMAGE = os.environ.get("RANGE42_INSTALLER_MAINTENANCE_TEST_IMAGE")
pytestmark = pytest.mark.skipif(
    not IMAGE, reason="requires explicit immutable local Docker acceptance image"
)


def wait_ready(module, plan, process):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        assert process.poll() is None, "Owned legacy API exited before readiness"
        try:
            if module.request(plan, "/v1/health/ready").get("ready") is True:
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    pytest.fail("Owned legacy API did not become ready")


def stop_process(process):
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


@pytest.fixture
def legacy_docker():
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", IMAGE)
    module = adoption()
    # Same absolute workspace/database is available on the host and in Docker.
    cache = Path("/home/ppa/.cache")
    fixture = Path(tempfile.mkdtemp(prefix="r42-adoption-test-", dir=cache))
    fixture.chmod(0o700)
    state = fixture / "state"
    workspace = fixture / "workspaces"
    home = fixture / "legacy-home"
    for directory in (state, workspace, home):
        directory.mkdir(mode=0o700)
    secret_directory = fixture / "secrets"
    secret_directory.mkdir(mode=0o700)
    vault_password = secret_directory / "vault-password"
    vault_password.write_text("fixture-only-vault-password\n")
    vault_password.chmod(0o600)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    raw = {
        "root": str(fixture / "managed"),
        "name": fixture.name,
        "image": IMAGE,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "state_dir": str(state),
        "secrets_dir": str(fixture / "secrets"),
        "workspace_host": str(workspace),
        "workspace_container": str(workspace),
        "database_container": str(workspace / ".range42.db"),
        "network_mode": "host",
        "listen_address": "127.0.0.1",
        "port": port,
        "cors_origins": ["http://127.0.0.1:3000"],
        "vault_password_host": str(vault_password),
        "vault_password_container": "/etc/range42/secrets/vault-password",
    }
    plan = module.validate_config(raw)
    from container_install import provision_credentials
    from container_apply import apply

    provision_credentials(
        Path(plan["secrets_dir"]),
        Path(plan["database_host"]),
        uid=plan["uid"],
        gid=plan["gid"],
    )
    environment = module.compose_document(plan, "fixture")["services"]["api"][
        "environment"
    ]
    environment.pop("RANGE42_MAINTENANCE_LOCK_FILE")
    environment.update(
        {
            "PATH": str(PYTHON.parent) + ":/usr/bin:/bin",
            "HOME": str(home),
            "PROJECT_ROOT_DIR": str(API),
            "PYTHONDONTWRITEBYTECODE": "1",
            "RANGE42_API_TOKEN_FILE": plan["secrets_dir"] + "/api-token",
            "RANGE42_CREDENTIAL_KEY_FILE": plan["secrets_dir"] + "/credential-key",
            "VAULT_PASSWORD_FILE": str(vault_password),
        }
    )
    log = (fixture / "legacy-private.log").open("xb")

    class OwnedService(module.SystemdCLI):
        """Transport substitute only: every process/state audit is inherited."""

        def __init__(self):
            super().__init__("range42-fixture.service", plan)
            self.process = None
            self.enabled = "enabled"
            self.events = []

        def command(self, *arguments):
            action = arguments[0]
            assert arguments[1] == self.unit
            self.events.append(action)
            running = self.process is not None and self.process.poll() is None
            if action == "show":
                if arguments[2:] == ("--property=EnvironmentFiles", "--value"):
                    return ""  # Fixture environment is supplied directly, with no env files.
                return "\n".join(
                    [
                        "MainPID=" + str(self.process.pid if running else 0),
                        "ActiveState=" + ("active" if running else "inactive"),
                        "SubState=" + ("running" if running else "dead"),
                        "KillMode=process",
                        "UnitFileState=" + self.enabled,
                        "TriggeredBy=",
                        "Result=success",
                    ]
                )
            if action == "cat":
                return "[Service]\nKillMode=process\nFixture=" + str(fixture) + "\n"
            if action in ("enable", "disable"):
                self.enabled = "enabled" if action == "enable" else "disabled"
                return ""
            if action == "stop":
                stop_process(self.process)
                return ""
            if action == "start":
                assert not running, "Refuse two legacy fixture processes"
                self.process = subprocess.Popen(
                    [
                        str(PYTHON),
                        str(API / "container_entrypoint.py"),
                        str(PYTHON),
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--workers",
                        "1",
                        "--log-level",
                        "warning",
                        "--timeout-graceful-shutdown",
                        "5",
                    ],
                    cwd=API,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
                wait_ready(module, plan, self.process)
                return ""
            raise AssertionError("Unexpected systemctl fixture operation")

    service = OwnedService()
    docker = module.DockerCLI()
    # Isolate Docker credentials too; all images are already local and never pulled.
    docker_config = fixture / "docker-config"
    docker_config.mkdir(mode=0o700)
    (docker_config / "config.json").write_text("{}")
    docker.environment.update(
        {"DOCKER_CONFIG": str(docker_config), "DOCKER_BUILDKIT": "0"}
    )
    images = []

    def owned_containers():
        identifiers = docker._run(
            [
                "ps",
                "-aq",
                "--no-trunc",
                "--filter",
                "label=org.range42.installation=" + plan["root"],
            ]
        ).splitlines()
        for identifier in identifiers:
            assert re.fullmatch("[0-9a-f]{64}", identifier)
            assert (
                docker.inspect(identifier)["Config"]["Labels"][
                    "org.range42.installation"
                ]
                == plan["root"]
            )
        return identifiers

    try:
        assert (
            docker._run(["image", "inspect", IMAGE, "--format", "{{.Id}}"]).strip()
            == IMAGE
        )
        service.command("start", service.unit)
        original_pid = service.process.pid
        database = Path(plan["database_host"])
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE adoption_sentinel (value TEXT NOT NULL)")
            db.execute("INSERT INTO adoption_sentinel VALUES ('original')")
        history = workspace / "history.jsonl"
        history.write_text("existing owned history\n")
        encrypted = workspace / "vault-probe.txt"
        encrypted.write_text("retained-vault-credential-works\n")
        subprocess.run(
            [
                str(PYTHON.parent / "ansible-vault"),
                "encrypt",
                "--vault-password-file",
                str(vault_password),
                str(encrypted),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        proof = {
            "version": 1,
            "unit": service.unit,
            "credentials": module.credentials(plan),
            **service.snapshot(),
        }
        assert proof["process"]["pid"] == original_pid
        assert module.request(plan, "/v1/admin/maintenance")["enabled"] is False
        yield {
            "module": module,
            "apply": apply,
            "raw": raw,
            "plan": plan,
            "proof": proof,
            "service": service,
            "docker": docker,
            "fixture": fixture,
            "images": images,
            "owned_containers": owned_containers,
            "history": history,
            "database": database,
            "original_pid": original_pid,
            "encrypted": encrypted,
        }
    finally:
        stop_process(service.process)
        for identifier in owned_containers():
            docker._run(["rm", "--force", identifier], timeout=30)
        assert owned_containers() == []
        # Host network must not have created a new Docker network.
        assert (
            docker._run(
                [
                    "network",
                    "ls",
                    "--quiet",
                    "--filter",
                    "label=org.range42.installation=" + plan["root"],
                ]
            ).strip()
            == ""
        )
        for identifier in images:
            assert (
                re.fullmatch(r"sha256:[0-9a-f]{64}", identifier) and identifier != IMAGE
            )
            inspected = json.loads(docker._run(["image", "inspect", identifier]))[0]
            assert inspected["Config"]["Labels"]["org.range42.adoption-fixture"] == str(
                fixture
            )
            docker._run(["image", "rm", "--no-prune", identifier], timeout=30)
        assert (
            docker._run(["image", "inspect", IMAGE, "--format", "{{.Id}}"]).strip()
            == IMAGE
        )
        log.close()
        shutil.rmtree(fixture)
        assert not fixture.exists()


def assert_preserved(legacy):
    with sqlite3.connect(legacy["database"]) as db:
        assert db.execute("SELECT value FROM adoption_sentinel").fetchall() == [
            ("original",)
        ]
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='failed_adoption'"
            ).fetchall()
            == []
        )
    assert legacy["history"].read_text() == "existing owned history\n"
    assert (
        legacy["module"].credentials(legacy["plan"]) == legacy["proof"]["credentials"]
    )


def test_real_systemd_adoption_preserves_paths_and_managed_repeat(legacy_docker):
    fixture = legacy_docker
    module, service, docker = fixture["module"], fixture["service"], fixture["docker"]
    assert module.adopt(
        fixture["raw"], fixture["proof"], docker=docker, service=service
    ) == {
        "status": "adopted",
        "changed": True,
    }
    service.assert_stopped()
    root = Path(fixture["plan"]["root"])
    record_path = root / "installation.json"
    before = record_path.read_bytes()
    record = json.loads(before)
    identifier = record["container_id"]
    assert fixture["owned_containers"]() == [identifier]
    info = docker.inspect(identifier)
    assert info["State"]["Running"] is True and info["Image"] == IMAGE
    assert info["HostConfig"]["NetworkMode"] == "host"
    assert info["HostConfig"]["PortBindings"] in (None, {})
    assert (
        "VAULT_PASSWORD_FILE=" + fixture["plan"]["vault_password_container"]
        in info["Config"]["Env"]
    )
    assert any(
        m["Source"] == fixture["plan"]["vault_password_host"]
        and m["Destination"] == fixture["plan"]["vault_password_container"]
        and not m["RW"]
        for m in info["Mounts"]
    )
    assert (
        docker._run(
            [
                "exec",
                identifier,
                "ansible-vault",
                "view",
                "--vault-password-file",
                fixture["plan"]["vault_password_container"],
                str(fixture["encrypted"]),
            ]
        ).strip()
        == "retained-vault-credential-works"
    )
    assert record["config"]["workspace_container"] == str(fixture["database"].parent)
    assert record["config"]["database_container"] == str(fixture["database"])
    assert any(
        m["Source"] == m["Destination"] == str(fixture["database"].parent)
        for m in info["Mounts"]
    )
    capability = module.request(fixture["plan"], "/v1/admin/maintenance")
    assert capability["enabled"] is True
    inode = (Path(fixture["plan"]["state_dir"]) / "maintenance.lock").stat().st_ino
    assert fixture["apply"](fixture["raw"]) == {"status": "unchanged", "changed": False}
    assert record_path.read_bytes() == before
    assert (
        Path(fixture["plan"]["state_dir"]) / "maintenance.lock"
    ).stat().st_ino == inode
    assert not (root / "pending.json").exists()
    assert service.events.count("stop") == 1
    assert_preserved(fixture)


def test_real_busy_artifact_audit_refuses_before_old_service_stop(legacy_docker):
    fixture = legacy_docker
    artifact = (
        fixture["database"].parent / "busy-workspace/runner/unrecorded/process.json"
    )
    artifact.parent.mkdir(parents=True, mode=0o700)
    artifact.write_text('{"pid":0}')
    with pytest.raises(ValueError, match="idle audit refused"):
        fixture["module"].adopt(
            fixture["raw"],
            fixture["proof"],
            docker=fixture["docker"],
            service=fixture["service"],
        )
    assert fixture["service"].process.pid == fixture["original_pid"]
    assert fixture["service"].process.poll() is None
    assert "stop" not in fixture["service"].events
    assert "disable" not in fixture["service"].events
    assert fixture["owned_containers"]() == []
    assert not Path(fixture["plan"]["root"]).exists()
    assert artifact.read_text() == '{"pid":0}'
    assert_preserved(fixture)


def test_real_failed_candidate_db_write_restores_original_service(legacy_docker):
    fixture = legacy_docker
    build = fixture["fixture"] / "failed-image"
    build.mkdir(mode=0o700)
    (build / "Dockerfile").write_text(
        "FROM "
        + IMAGE
        + "\nLABEL org.range42.adoption-fixture="
        + json.dumps(str(fixture["fixture"]))
        + "\nCOPY fail.py /fixture-fail.py\n"
        'ENTRYPOINT ["python", "/fixture-fail.py"]\n'
    )
    (build / "fail.py").write_text(
        "import os,sqlite3\n"
        'path=os.environ["RANGE42_DB_URL"].removeprefix("sqlite+aiosqlite:///")\n'
        "with sqlite3.connect(path) as db:\n"
        " db.execute(\"UPDATE adoption_sentinel SET value='candidate-write'\")\n"
        ' db.execute("CREATE TABLE IF NOT EXISTS failed_adoption (value TEXT)")\n'
        'print("owned-candidate-db-write-complete",flush=True)\n'
        "raise SystemExit(23)\n"
    )
    image = (
        fixture["docker"]
        ._run(["build", "--quiet", "--network", "none", str(build)], timeout=60)
        .strip()
    )
    fixture["images"].append(image)
    with pytest.raises(
        ValueError, match="original database and systemd service restored"
    ):
        fixture["module"].adopt(
            {**fixture["raw"], "image": image},
            fixture["proof"],
            docker=fixture["docker"],
            service=fixture["service"],
        )
    identifiers = fixture["owned_containers"]()
    assert len(identifiers) == 1
    info = fixture["docker"].inspect(identifiers[0])
    assert info["State"]["Running"] is False
    assert info["State"]["ExitCode"] == 23
    lines = fixture["docker"]._run(["logs", identifiers[0]]).splitlines()
    assert lines and set(lines) == {"owned-candidate-db-write-complete"}
    service = fixture["service"]
    assert (
        service.process.poll() is None
        and service.process.pid != fixture["original_pid"]
    )
    assert service.enabled == fixture["proof"]["enabled"]
    assert (
        fixture["module"].request(fixture["plan"], "/v1/health/ready")["ready"] is True
    )
    assert (
        fixture["module"].request(fixture["plan"], "/v1/admin/maintenance")["enabled"]
        is False
    )
    root = Path(fixture["plan"]["root"])
    assert not (root / "installation.json").exists()
    assert not (root / "pending.json").exists()
    failures = list((root / "backups").glob("*/failure.json"))
    assert (
        len(failures) == 1
        and json.loads(failures[0].read_text())["status"] == "rolled_back"
    )
    assert (Path(fixture["plan"]["state_dir"]) / "maintenance.lock").read_bytes() == b""
    assert_preserved(fixture)
