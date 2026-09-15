"""Explicit offline adoption of a reviewed systemd API; never an implicit fresh start."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import stat
import subprocess
import tarfile

from container_apply import (
    backup_database,
    compose_document,
    create_candidate,
    credentials,
    installation_lock,
    read_json,
    request,
    restore_database,
    snapshot,
    stage,
    tree_hash,
    validate_config,
    verify_image_protocol,
    verify_ready,
    wait_health,
    write_json,
    INTERNAL_READY,
)
from container_maintenance import DockerCLI, host_admission


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_adoption_proof(plan, proof):
    fields = {
        "version",
        "unit",
        "process",
        "config_sha256",
        "environment_sha256",
        "credentials",
        "enabled",
    }
    if not isinstance(proof, dict) or set(proof) != fields or proof["version"] != 1:
        raise ValueError("Systemd adoption requires an explicit captured proof")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+\.service", proof["unit"]):
        raise ValueError("Systemd adoption requires one ordinary service unit")
    process = proof["process"]
    if (
        not isinstance(process, dict)
        or set(process) != {"pid", "start_time", "boot_id"}
        or type(process["pid"]) is not int
        or process["pid"] <= 0
        or not isinstance(process["start_time"], str)
        or not process["start_time"].isdigit()
        or not isinstance(process["boot_id"], str)
        or not process["boot_id"]
    ):
        raise ValueError("Systemd process proof is invalid")
    for field in ("config_sha256", "environment_sha256"):
        if not isinstance(proof[field], str) or not re.fullmatch(
            "[0-9a-f]{64}", proof[field]
        ):
            raise ValueError("Systemd configuration proof is invalid")
    if proof["enabled"] not in ("enabled", "disabled"):
        raise ValueError("Systemd enablement cannot be restored safely")
    if credentials(plan) != proof["credentials"]:
        raise ValueError("Original credential bytes changed; adoption refused")


def validate_environment(plan, environment):
    expected = compose_document(plan, "adoption")["services"]["api"]["environment"]
    optional = (
        "API_BACKEND_INVENTORY_DIR",
        "API_BACKEND_PUBLIC_PLAYBOOKS_DIR",
        "API_BACKEND_WWWAPP_PLAYBOOKS_DIR",
        "RANGE42_BUNDLE_DIR",
        "RANGE42_BUNDLE_RUNTIME_MANIFEST",
        "RANGE42_WORKSPACE_TEMPLATE_DIR",
        "RANGE42_PROXMOX_CA_FILE",
        "RANGE42_INVENTORY__DOCKER__CTF",
        "ANSIBLE_CONFIG",
        "ANSIBLE_COLLECTIONS_PATH",
        "ANSIBLE_ROLES_PATH",
    )
    if any(environment.get(key) and key not in expected for key in optional):
        raise ValueError(
            "Existing optional configuration needs its explicit candidate binding"
        )
    for key, value in expected.items():
        if key in ("HOME", "RANGE42_MAINTENANCE_LOCK_FILE"):
            continue
        if key == "RANGE42_API_TOKEN_FILE":
            value = plan["secrets_dir"] + "/api-token"
        if key == "RANGE42_CREDENTIAL_KEY_FILE":
            value = plan["secrets_dir"] + "/credential-key"
        actual = environment.get(
            key,
            "github.com,gitlab.com,codeberg.org"
            if key == "RANGE42_GIT_ALLOWED_HOSTS"
            else "",
        )
        if key in ("RANGE42_CORS_ORIGINS", "RANGE42_GIT_ALLOWED_HOSTS"):
            matches = {s.strip() for s in actual.split(",") if s.strip()} == {
                s.strip() for s in value.split(",") if s.strip()
            }
        else:
            matches = actual == value
        if not matches:
            raise ValueError(
                "Existing application configuration or persistent binding differs from the adoption plan"
            )
    unsupported = (
        "RANGE42_API_PRINCIPALS_FILE",
        "RANGE42_GIT_SECRET_DIR",
        "RANGE42_GIT_SECRET_ENV_ALLOWLIST",
        "RANGE42_API_TOKEN",
        "RANGE42_CREDENTIAL_KEY",
        "API_BACKEND_VAULT_FILE",
        "VAULT_PASSWORD",
        "VAULT_PASSWORD_FILE",
        "CORS_ORIGIN_REGEX",
    )
    if any(environment.get(key) for key in unsupported):
        raise ValueError(
            "Existing authentication, Git or vault policy needs an explicit supported migration configuration"
        )
    for key in ("RANGE42_AUDIT_ENABLED", "RANGE42_GIT_ALLOW_HTTP"):
        if environment.get(key, "").lower() not in ("", "0", "false", "no"):
            raise ValueError("Existing policy must not be silently changed by adoption")
    if environment.get("RANGE42_AUTO_START_ATTEMPTS", "1") not in ("1", "true", "yes"):
        raise ValueError("Existing attempt configuration is not the candidate default")
    if environment.get("RANGE42_MAINTENANCE_LOCK_FILE"):
        raise ValueError(
            "This offline adoption path requires the reviewed disabled legacy maintenance gate"
        )


IDLE_AUDIT = """import sqlite3
from pathlib import Path
from app.core.config import settings
from app.core.locks import ProvisioningLock
from app.core.maintenance_guard import assert_idle
database = Path(settings.db_url.removeprefix('sqlite+aiosqlite:///'))
with ProvisioningLock(settings.workspace_root / '.locks'):
    with sqlite3.connect(database.as_uri()+'?mode=rw', uri=True, timeout=1) as db:
        db.execute('BEGIN IMMEDIATE')
        assert_idle(db, settings.workspace_root)
        db.rollback()
print('idle')
"""


class SystemdCLI:
    def __init__(self, unit, plan):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+\.service", unit):
            raise ValueError("Invalid systemd unit")
        self.unit, self.plan = unit, plan
        self.environment = None
        self.python = None

    def command(self, *arguments):
        result = subprocess.run(
            ["systemctl", *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            raise ValueError(
                "Systemd command failed; inspect the retained adoption record"
            )
        return result.stdout

    def properties(self):
        output = self.command(
            "show",
            self.unit,
            "--property=MainPID,ActiveState,SubState,KillMode,UnitFileState,TriggeredBy,Result",
        )
        return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)

    def configuration(self):
        unit = self.command("cat", self.unit)
        values = self.command(
            "show", self.unit, "--property=EnvironmentFiles", "--value"
        )
        files = {}
        for value in shlex.split(values):
            if value.startswith("("):
                continue
            path = Path(value)
            if not path.is_absolute() or path != path.resolve() or not path.is_file():
                raise ValueError(
                    "Legacy environment files must be explicit ordinary paths"
                )
            files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"unit": unit, "environment_files": files}

    def snapshot(self):
        values = self.properties()
        if (
            values["ActiveState"] != "active"
            or values["SubState"] != "running"
            or values["KillMode"] != "process"
            or values["TriggeredBy"]
            or values["UnitFileState"] not in ("enabled", "disabled")
        ):
            raise ValueError(
                "Legacy service must be running, preserve detached runners and have explicit enablement"
            )
        pid = int(values["MainPID"])
        process = Path("/proc") / str(pid)
        if process.stat().st_uid != self.plan["uid"]:
            raise ValueError(
                "Legacy API process owner does not match the container UID"
            )
        self.environment = dict(
            item.decode().split("=", 1)
            for item in (process / "environ").read_bytes().split(b"\0")
            if b"=" in item
        )
        self.python = (process / "cmdline").read_bytes().split(b"\0")[0].decode()
        if not Path(self.python).is_absolute() or not Path(self.python).name.startswith(
            "python"
        ):
            raise ValueError("Legacy API Python executable cannot be verified")
        validate_environment(self.plan, self.environment)
        start = (process / "stat").read_text().rsplit(")", 1)[1].split()[19]
        return {
            "process": {
                "pid": pid,
                "start_time": start,
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            },
            "config_sha256": digest(self.configuration()),
            "environment_sha256": digest(self.environment),
            "enabled": values["UnitFileState"],
        }

    def verify(self, proof):
        current = self.snapshot()
        if any(current[key] != proof[key] for key in current):
            raise ValueError(
                "Legacy service identity or configuration changed after review"
            )

    def installed_python(self, code):
        if os.geteuid() == 0:
            identity = {
                "user": self.plan["uid"],
                "group": self.plan["gid"],
                "extra_groups": [],
            }
        elif (os.geteuid(), os.getegid()) == (self.plan["uid"], self.plan["gid"]):
            identity = {}
        else:
            raise ValueError(
                "Installed audit requires the original application identity"
            )
        return subprocess.run(
            [self.python, "-c", code],
            cwd=self.environment["PROJECT_ROOT_DIR"],
            env={**self.environment, "PYTHONDONTWRITEBYTECODE": "1"},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=45,
            **identity,
        )

    def audit(self):
        result = self.installed_python(IDLE_AUDIT)
        if result.returncode or result.stdout.strip() != "idle":
            raise ValueError(
                "Installed strict idle audit refused; no migration may proceed"
            )

    def stop(self):
        self.command("disable", self.unit)
        self.command("stop", self.unit)
        self.assert_stopped()

    def assert_stopped(self):
        values = self.properties()
        if (
            values["ActiveState"] != "inactive"
            or values["MainPID"] != "0"
            or values["Result"] != "success"
            or values["UnitFileState"] != "disabled"
        ):
            raise ValueError("Legacy service did not stop cleanly; migration refused")

    def restore(self, enabled):
        if enabled == "enabled":
            self.command("enable", self.unit)
        self.command("start", self.unit)

    def prepare_restore(self, proof):
        if (
            digest(self.configuration()) != proof["config_sha256"]
            or credentials(self.plan) != proof["credentials"]
        ):
            raise ValueError(
                "Original service configuration changed; offline recovery required"
            )
        result = self.installed_python(INTERNAL_READY)
        if result.returncode or result.stdout.strip() != '{"ready": true}':
            raise ValueError(
                "Original runtime and data readiness failed before reopening systemd"
            )

    def recover_stop(self, proof):
        values = self.properties()
        if (
            values["ActiveState"] == "active"
            and int(values["MainPID"]) == proof["process"]["pid"]
        ):
            current = self.snapshot()
            if any(
                current[key] != proof[key]
                for key in ("process", "config_sha256", "environment_sha256")
            ):
                raise ValueError(
                    "Original running service identity changed; recovery refused"
                )
            if proof["enabled"] == "enabled":
                self.command("enable", self.unit)
            return
        if (
            values["ActiveState"] == "inactive"
            and values["MainPID"] == "0"
            and values["Result"] == "success"
        ):
            self.audit()
            self.prepare_restore(proof)
            self.restore(proof["enabled"])
            if not self.ready():
                raise ValueError(
                    "Restored service readiness failed after reopening; do not restore data again"
                )
            return
        raise ValueError(
            "Service stop outcome is uncertain; original data retained for offline recovery"
        )

    def ready(self):
        return request(self.plan, "/v1/health/ready").get("ready") is True


def capture(raw, unit):
    plan = validate_config(raw)
    service = SystemdCLI(unit, plan)
    proof = {
        "version": 1,
        "unit": unit,
        "credentials": credentials(plan),
        **service.snapshot(),
    }
    service.audit()
    validate_adoption_proof(plan, proof)
    return proof


def adoption_file(path):
    path = Path(path)
    info = path.lstat()
    if (
        not path.is_absolute()
        or path != path.resolve()
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError(
            "Adoption proof must be a private regular file owned by the installer"
        )
    return read_json(path)


def workspace_digest(plan):
    database = Path(plan["database_host"])
    return tree_hash(
        Path(plan["workspace_host"]),
        exclude={
            database,
            database.with_name(database.name + "-wal"),
            database.with_name(database.name + "-shm"),
        },
    )


def database_digest(path):
    with sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True) as db:
        result = {}
        for (name,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [
                row[1] for row in db.execute("PRAGMA table_info(" + quoted + ")")
            ]
            rows = sorted(
                json.dumps(
                    row,
                    default=lambda value: {"bytes": value.hex()},
                    separators=(",", ":"),
                )
                for row in db.execute("SELECT * FROM " + quoted)
            )
            result[name] = {
                "columns": columns,
                "rows": len(rows),
                "sha256": digest(rows),
            }
        return result


def adopt(raw, proof, *, docker=None, service=None):
    plan = validate_config(raw)
    validate_adoption_proof(plan, proof)
    service = service or SystemdCLI(proof["unit"], plan)
    service.verify(proof)
    service.audit()
    root = Path(plan["root"])
    if root.exists() and any(root.iterdir()):
        raise ValueError(
            "Adoption requires a new managed root; existing records need explicit recovery"
        )
    for field in ("state_dir", "workspace_host"):
        path = Path(plan[field])
        info = path.stat()
        if (
            path != path.resolve()
            or not path.is_dir()
            or (info.st_uid, info.st_gid) != (plan["uid"], plan["gid"])
            or info.st_mode & 0o022
        ):
            raise ValueError("Existing state ownership or binding cannot be preserved")
    for field in ("runtime_dir", "workspace_template_dir"):
        if plan[field]:
            tree_hash(Path(plan[field]))
    docker = docker or DockerCLI()
    image = verify_image_protocol(docker, plan["image"])
    root.mkdir(mode=0o700, parents=True)
    with installation_lock(root):
        release_id, release, _ = stage(plan, root)
        backup = root / "backups" / release_id
        backup.mkdir(mode=0o700, parents=True)
        pending = {
            "version": 1,
            "status": "adopting-systemd",
            "config": plan,
            "legacy": proof,
            "release_dir": str(release),
            "backup": str(backup),
        }
        write_json(root / "pending.json", pending)
        identifier = None
        stop_attempted = False
        try:
            service.verify(proof)
            stop_attempted = True
            service.stop()
            service.audit()
            service.assert_stopped()
            if credentials(plan) != proof["credentials"]:
                raise ValueError("Original credentials changed before backup")
            database = Path(plan["database_host"])
            backup_database(database, backup / "database.sqlite")
            original_database = database_digest(database)
            write_json(backup / "database-records.json", original_database)
            with tarfile.open(backup / "state.tar", "x") as archive:
                archive.add(plan["state_dir"], arcname="state", recursive=True)
            with tarfile.open(backup / "credentials.tar", "x") as archive:
                archive.add(plan["secrets_dir"], arcname="secrets", recursive=True)
            (backup / "state.tar").chmod(0o600)
            (backup / "credentials.tar").chmod(0o600)
            workspace_hash = workspace_digest(plan)
            lock = Path(plan["state_dir"]) / "maintenance.lock"
            if not lock.exists() and not lock.is_symlink():
                fd = os.open(
                    lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                )
                os.fchown(fd, plan["uid"], plan["gid"])
                os.close(fd)
            with host_admission(lock, uid=plan["uid"], gid=plan["gid"]) as gate:
                gate.begin_intent()
                try:
                    service.assert_stopped()
                    identifier = create_candidate(docker, release, plan)
                    pending["container_id"] = identifier
                    write_json(root / "pending.json", pending)
                    docker._run(["start", identifier], timeout=30)
                    wait_health(plan, docker, identifier)
                    verify_ready(docker, identifier)
                    if (
                        database_digest(database) != original_database
                        or workspace_digest(plan) != workspace_hash
                    ):
                        raise ValueError(
                            "Existing database or workspace content changed during adoption"
                        )
                    info = docker.inspect(identifier)
                    if (
                        info["Image"] != image
                        or credentials(plan) != proof["credentials"]
                    ):
                        raise ValueError(
                            "Candidate image or original credentials changed"
                        )
                    service.assert_stopped()
                    gate.verify()
                    record = {
                        "version": 1,
                        "status": "ready",
                        "config": plan,
                        "image_id": image,
                        "container_id": identifier,
                        "release_id": release_id,
                        "release_dir": str(release),
                        "release_sha256": tree_hash(release),
                        "credentials": credentials(plan),
                        "container_snapshot": snapshot(info),
                        "legacy_systemd": {"proof": proof, "backup": str(backup)},
                    }
                    write_json(root / "installation.json", record)
                    (root / "pending.json").unlink()
                    gate.complete()
                except Exception:
                    if identifier:
                        docker.stop(identifier)
                        if docker.inspect(identifier)["State"]["Running"]:
                            raise ValueError(
                                "Candidate stop is unverified; retain the fence and recover offline"
                            ) from None
                    if workspace_digest(plan) != workspace_hash:
                        raise ValueError(
                            "Workspace changed during failed adoption; manual recovery required"
                        ) from None
                    restore_database(backup / "database.sqlite", database, plan)
                    service.prepare_restore(proof)
                    record_file = root / "installation.json"
                    if record_file.exists():
                        if read_json(record_file).get("container_id") != identifier:
                            raise ValueError(
                                "Managed record changed; retain offline recovery state"
                            )
                        record_file.unlink()
                    pending["status"] = "restored_offline"
                    write_json(backup / "failure.json", pending)
                    write_json(root / "pending.json", pending)
                    gate.complete()
                    service.restore(proof["enabled"])
                    if not service.ready():
                        raise ValueError(
                            "Original service readiness failed after reopening; do not restore admitted data"
                        )
                    pending["status"] = "rolled_back"
                    write_json(backup / "failure.json", pending)
                    (root / "pending.json").unlink(missing_ok=True)
                    raise ValueError(
                        "Candidate failed; original database and systemd service restored"
                    ) from None
        except Exception:
            # Before candidate creation the original service is still the sole owner.
            # A candidate/stop/rollback failure retains pending state and its fence.
            if stop_attempted and identifier is None:
                service.recover_stop(proof)
            raise
    if request(plan, "/v1/health/ready").get("ready") is not True:
        raise ValueError(
            "Adopted API readiness failed after admission; do not roll back admitted writes"
        )
    return {"status": "adopted", "changed": True}
