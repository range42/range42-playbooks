"""Managed, immutable local-container installation; credentials never enter output."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import time
import urllib.error
import urllib.request
import uuid

from container_install import _secret, provision_credentials
from container_maintenance import PROTOCOL, DockerCLI, host_admission, stopped_container
from container_plan import compose_document, validate_config


@contextmanager
def installation_lock(root: Path):
    if root != root.resolve() or not root.is_dir():
        raise ValueError("Installation root must be an ordinary local directory")
    path = root / ".installation.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("Installation lock must be private and owned")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Installation is busy") from None
        if path.lstat().st_ino != info.st_ino:
            raise ValueError("Installation lock changed")
        yield
    finally:
        os.close(fd)


def tree_hash(root: Path) -> str:
    root = root.absolute()
    if root != root.resolve() or not root.is_dir():
        raise ValueError("Release tree must be an ordinary local directory")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = str(path.relative_to(root))
        if stat.S_ISLNK(info.st_mode):
            try:
                inside = path.resolve(strict=True).is_relative_to(root)
            except (OSError, RuntimeError):
                inside = False
            if not inside:
                raise ValueError(
                    "Release link escapes its complete tree or is unreadable"
                )
            value = ["link", relative, os.readlink(path)]
        elif stat.S_ISDIR(info.st_mode):
            value = ["directory", relative]
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            value = [
                "file",
                relative,
                info.st_mode & 0o111,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            ]
        else:
            raise ValueError("Release contains a special file or hard link")
        digest.update((json.dumps(value, separators=(",", ":")) + "\n").encode())
    return digest.hexdigest()


def copy_tree(source: Path, destination: Path, *, uid: int, gid: int):
    original = tree_hash(source)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Release destination already exists")
    shutil.copytree(source, destination, symlinks=True)
    for path in [destination, *destination.rglob("*")]:
        if not path.is_symlink():
            mode = 0o700 if path.is_dir() else 0o600 | (path.stat().st_mode & 0o111)
            path.chmod(mode)
        os.chown(path, uid, gid, follow_symlinks=False)
    if tree_hash(destination) != original or tree_hash(source) != original:
        raise ValueError("Release source or staged bytes changed during copying")


def write_json(path: Path, value: dict):
    temporary = path.with_name("." + path.name + "-" + uuid.uuid4().hex)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > 1024 * 1024
    ):
        raise ValueError("Managed record is not a bounded regular file")
    return json.loads(path.read_bytes())


def credentials(plan):
    result = {}
    for name in ("api-token", "credential-key"):
        path = Path(plan["secrets_dir"]) / name
        if _secret(path) is None:
            raise ValueError("Original credential files are missing")
        info = path.stat()
        if (info.st_uid, info.st_gid) != (
            plan["uid"],
            plan["gid"],
        ) or info.st_mode & 0o077:
            raise ValueError("Original credential permissions changed")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def snapshot(info):
    return {
        "Image": info["Image"],
        "Config": info["Config"],
        "HostConfig": info["HostConfig"],
        "Mounts": sorted(
            info["Mounts"], key=lambda row: json.dumps(row, sort_keys=True)
        ),
    }


def request(plan, path, *, authenticated=True):
    address = plan["listen_address"]
    address = (
        "127.0.0.1" if address == "0.0.0.0" else "::1" if address == "::" else address
    )
    if ":" in address:
        address = "[" + address + "]"
    headers = {}
    if authenticated:
        headers["Authorization"] = "Bearer " + _secret(
            Path(plan["secrets_dir"]) / "api-token"
        )
    req = urllib.request.Request(
        f"http://{address}:{plan['port']}{path}", headers=headers
    )
    with urllib.request.urlopen(req, timeout=3) as response:
        if response.status != 200:
            raise ValueError("Managed API did not return success")
        return json.loads(response.read(1024 * 1024))


def verify_image_protocol(docker, reference):
    image = json.loads(docker._run(['image', 'inspect', reference]))[0]['Id']
    if not isinstance(image, str) or len(image) != 71 or not image.startswith('sha256:') or any(char not in '0123456789abcdef' for char in image[7:]):
        raise ValueError('Candidate immutable image identity is invalid')
    protocol = docker._run(['run', '--rm', '--network', 'none', '--read-only',
                           '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                           '--entrypoint', 'python', image, '-c',
                           'from app.core.maintenance import PROTOCOL; print(PROTOCOL)'], timeout=30)
    if protocol.strip() != PROTOCOL:
        raise ValueError('Candidate maintenance protocol is unsupported; a durable-intent v2 image is required')
    return image


def wait_health(plan, docker, identifier):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if not docker.inspect(identifier)["State"]["Running"]:
            raise ValueError(
                "Candidate stopped before becoming healthy; private state retained"
            )
        try:
            if request(plan, "/v1/health", authenticated=False).get("status") == "ok":
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise ValueError("Candidate health timed out; private state retained")


# Run under the image environment while HTTP admission remains fenced. The backend
# route performs its real database, credential and configured-host checks. Nothing
# from its diagnostic return value is forwarded to the installer.
INTERNAL_READY = """import asyncio, json
from app.core.db import get_session_factory
from app.routes.v1.health import readiness
from app.core.maintenance import PROTOCOL
assert PROTOCOL == 'flock-http-intent-v2'
async def main():
    async with get_session_factory()() as session:
        result = await readiness(session)
        assert result.get('ready') is True
    import os
    if os.environ.get('RANGE42_BUNDLE_RUNTIME_MANIFEST'):
        from app.core.bundle_runtime import runtime_snapshot
        runtime_snapshot()
    print(json.dumps({'ready': True}))
asyncio.run(main())
"""


def verify_ready(docker, identifier):
    raw = docker._run(["exec", identifier, "python", "-c", INTERNAL_READY], timeout=45)
    if json.loads(raw) != {"ready": True}:
        raise ValueError("Candidate internal readiness did not succeed")


def verify_managed(docker, record, plan):
    if record.get("version") != 1 or record.get("status") != "ready":
        raise ValueError("Managed installation requires explicit recovery")
    if credentials(record["config"]) != record["credentials"]:
        raise ValueError(
            "Original credential bytes changed; restore them before installation"
        )
    release = Path(record["release_dir"])
    if (
        release.parent != Path(plan["root"]) / "releases"
        or tree_hash(release) != record["release_sha256"]
    ):
        raise ValueError("Installed release bytes or binding changed")
    info = docker.inspect(record["container_id"])
    if (
        not info["State"]["Running"]
        or info["State"].get("Paused")
        or snapshot(info) != record["container_snapshot"]
    ):
        raise ValueError("Managed container identity or persistent binding changed")
    if request(record["config"], "/v1/health/ready").get("ready") is not True:
        raise ValueError("Managed API readiness failed")
    return info


def stage(plan, root):
    release_id = uuid.uuid4().hex
    release = root / "releases" / release_id
    release.mkdir(mode=0o700, parents=True)
    bound = dict(plan)
    for field, target in [
        ("runtime_dir", "runtime"),
        ("workspace_template_dir", "workspace-template"),
    ]:
        if plan[field]:
            copy_tree(
                Path(plan[field]), release / target, uid=plan["uid"], gid=plan["gid"]
            )
            bound[field] = str(release / target)
    document = compose_document(bound, release_id)
    document["networks"] = {
        "default": {"labels": {"org.range42.installation": plan["root"]}}
    }
    write_json(release / "compose.json", document)
    return release_id, release, bound


def create_candidate(docker, release, plan):
    docker._run(
        [
            "compose",
            "--project-name",
            plan["name"] + "-" + release.name[:12],
            "--file",
            str(release / "compose.json"),
            "create",
            "--no-build",
            "--pull",
            "never",
        ],
        timeout=60,
    )
    ids = docker._run(
        [
            "compose",
            "--project-name",
            plan["name"] + "-" + release.name[:12],
            "--file",
            str(release / "compose.json"),
            "ps",
            "--all",
            "--quiet",
            "api",
        ]
    ).splitlines()
    if len(ids) != 1:
        raise ValueError("Candidate immutable container ID is unavailable")
    identifier = ids[0]
    info = docker.inspect(identifier)
    if (
        info["State"]["Running"]
        or info["Config"]["Labels"].get("org.range42.installation") != plan["root"]
    ):
        raise ValueError("Candidate container ownership is unknown")
    return identifier


def backup_database(source: Path, backup: Path):
    if source != source.resolve() or not stat.S_ISREG(source.lstat().st_mode):
        raise ValueError("Existing database must be an ordinary local file")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as old:
        with sqlite3.connect(backup) as destination:
            old.backup(destination)
    backup.chmod(0o600)
    with backup.open("rb") as stream:
        os.fsync(stream.fileno())


def restore_database(backup: Path, source: Path, plan):
    if source != source.resolve():
        raise ValueError("Database binding changed; automatic restoration refused")
    temporary = source.with_name(".restore-" + uuid.uuid4().hex)
    shutil.copyfile(backup, temporary)
    temporary.chmod(0o600)
    os.chown(temporary, plan["uid"], plan["gid"])
    for suffix in ("-wal", "-shm"):
        sibling = source.with_name(source.name + suffix)
        if sibling.exists():
            if not stat.S_ISREG(sibling.lstat().st_mode):
                raise ValueError("Database journal path changed; restoration refused")
            sibling.unlink()
    os.replace(temporary, source)


def managed_update(docker, record, plan):
    original = record["config"]
    stable = (
        "root",
        "name",
        "uid",
        "gid",
        "state_dir",
        "workspace_host",
        "workspace_container",
        "database_container",
        "database_host",
        "secrets_dir",
    )
    if any(plan[key] != original[key] for key in stable):
        raise ValueError(
            "Guarded update cannot relocate persistent bindings or credentials"
        )
    image = verify_image_protocol(docker, plan["image"])
    root = Path(plan["root"])
    release_id, release, _ = stage(plan, root)
    proof = request(original, "/v1/admin/maintenance")
    identifier = None
    # The original host admission inode stays locked throughout migration,
    # candidate checks, record commit, or DB restoration and old-ID restart.
    with stopped_container(
        docker,
        record["container_id"],
        proof,
        state_dir=Path(plan["state_dir"]),
        installation_root=root,
        uid=plan["uid"],
        gid=plan["gid"],
    ) as gate:
        backup = root / "backups" / release_id
        backup.mkdir(mode=0o700, parents=True)
        database = Path(plan["database_host"])
        backup_database(database, backup / "database.sqlite")
        write_json(backup / "installation.json", record)
        pending = {
            "version": 1,
            "status": "updating",
            "release_dir": str(release),
            "previous_container_id": record["container_id"],
            "backup": str(backup),
        }
        write_json(root / "pending.json", pending)
        try:
            identifier = create_candidate(docker, release, plan)
            pending["container_id"] = identifier
            write_json(root / "pending.json", pending)
            docker._run(["start", identifier], timeout=30)
            wait_health(plan, docker, identifier)
            verify_ready(docker, identifier)
            info = docker.inspect(identifier)
            if info["Image"] != image:
                raise ValueError("Candidate immutable image changed")
            gate.verify()
            replacement = {
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
            }
            write_json(root / "installation.json", replacement)
            (root / "pending.json").unlink()
            gate.complete()
        except Exception:
            if identifier:
                docker.stop(identifier)
                if docker.inspect(identifier)["State"]["Running"]:
                    raise ValueError(
                        "Candidate stop failed; retain admission and inspect private recovery state"
                    ) from None
            restore_database(backup / "database.sqlite", database, original)
            docker._run(["start", record["container_id"]], timeout=30)
            wait_health(original, docker, record["container_id"])
            verify_ready(docker, record["container_id"])
            gate.verify()
            write_json(root / "installation.json", record)
            # Retain the failed candidate and backup as private diagnostic evidence.
            pending["status"] = "rolled_back"
            write_json(backup / "failure.json", pending)
            (root / "pending.json").unlink(missing_ok=True)
            gate.complete()
            raise ValueError(
                "Candidate failed; original database and managed container restored"
            ) from None
    if request(plan, "/v1/health/ready").get("ready") is not True:
        raise ValueError(
            "Updated API readiness failed after cutover; do not roll back admitted writes"
        )
    return {"status": "updated", "changed": True}


def apply(raw: dict, *, operation="apply"):
    if operation not in ("apply", "fresh", "update"):
        raise ValueError(
            "Unknown installer action; legacy adoption requires offline review"
        )
    plan = validate_config(raw)
    root = Path(plan["root"])
    record_path = root / "installation.json"
    # Prove inputs and unknown data before creating any installation state.
    for field in ("runtime_dir", "workspace_template_dir"):
        if plan[field]:
            tree_hash(Path(plan[field]))
    if not record_path.exists():
        if root.exists() and any(root.iterdir()):
            raise ValueError("Refusing unmanaged or unknown legacy installation")
        for field in ("state_dir", "workspace_host", "secrets_dir"):
            path = Path(plan[field])
            if path.exists() and any(path.iterdir()):
                raise ValueError("Existing state needs explicit reviewed adoption")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with installation_lock(root):
        if (root / "pending.json").exists() or (root / "pending.json").is_symlink():
            raise ValueError(
                "An incomplete pending installation requires explicit recovery"
            )
        docker = DockerCLI()
        if record_path.exists():
            record = read_json(record_path)
            verify_managed(docker, record, plan)
            if operation == "fresh":
                raise ValueError(
                    "Fresh installation cannot replace a managed container"
                )
            changed = record["config"] != plan
            for field, target in [
                ("runtime_dir", "runtime"),
                ("workspace_template_dir", "workspace-template"),
            ]:
                if plan[field] and (
                    not (Path(record["release_dir"]) / target).exists()
                    or tree_hash(Path(plan[field]))
                    != tree_hash(Path(record["release_dir"]) / target)
                ):
                    changed = True
            if changed:
                if operation != "update":
                    raise ValueError(
                        "Changed managed configuration requires a guarded update"
                    )
                return managed_update(docker, record, plan)
            return {"status": "unchanged", "changed": False}
        if operation == "update":
            raise ValueError("Guarded update requires an existing managed installation")
        image = verify_image_protocol(docker, plan["image"])
        for field in ("state_dir", "workspace_host"):
            path = Path(plan[field])
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.chmod(0o700)
            os.chown(path, plan["uid"], plan["gid"])
        provision_credentials(
            Path(plan["secrets_dir"]),
            Path(plan["database_host"]),
            uid=plan["uid"],
            gid=plan["gid"],
        )
        lock = Path(plan["state_dir"]) / "maintenance.lock"
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.fchown(fd, plan["uid"], plan["gid"])
        os.close(fd)
        release_id, release, bound = stage(plan, root)
        pending = {
            "version": 1,
            "status": "preparing",
            "config": plan,
            "release_dir": str(release),
        }
        write_json(root / "pending.json", pending)
        with host_admission(lock, uid=plan["uid"], gid=plan["gid"]) as gate:
            gate.begin_intent()
            identifier = create_candidate(docker, release, plan)
            pending["container_id"] = identifier
            write_json(root / "pending.json", pending)
            try:
                docker._run(["start", identifier], timeout=30)
                wait_health(plan, docker, identifier)
                verify_ready(docker, identifier)
                info = docker.inspect(identifier)
                if info["Image"] != image:
                    raise ValueError("Candidate immutable image changed")
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
                }
                write_json(record_path, record)
                (root / "pending.json").unlink()
                gate.complete()
            except Exception:
                docker.stop(identifier)
                if docker.inspect(identifier)["State"]["Running"]:
                    raise ValueError("Candidate remains running; durable maintenance intent retained") from None
                raise
        if request(plan, "/v1/health/ready").get("ready") is not True:
            raise ValueError("Installed API readiness failed")
        return {"status": "ready", "changed": True}


def main():
    os.umask(0o077)
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError("Installer request exceeds its bound")
        request_body = json.loads(raw)
        if not isinstance(request_body, dict) or set(request_body) != {
            "config",
            "operation",
        }:
            raise ValueError("Installer needs explicit config and operation")
        result = apply(request_body["config"], operation=request_body["operation"])
    except ValueError as exc:
        # ValueError messages are fixed installer validation strings. JSON decoder
        # errors are replaced; raw process stderr and credentials never escape.
        message = (
            "Invalid installer JSON"
            if isinstance(exc, json.JSONDecodeError)
            else str(exc)
        )
        print(json.dumps({"error": message}))
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "error": "Managed installation failed; inspect private state before retry"
                }
            )
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
