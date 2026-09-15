"""Opt-in actual Ansible bundle → disposable local Docker fresh/repeat acceptance."""

import hashlib
import fcntl
import sqlite3
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundles/admin/software.install.deployer_api_backend"
IMAGE = os.environ.get("RANGE42_INSTALLER_MAINTENANCE_TEST_IMAGE")
pytestmark = pytest.mark.skipif(
    not IMAGE, reason="requires explicit immutable local acceptance image"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_ansible_fresh_repeat_and_changed_managed_state_refusal(tmp_path):
    assert "container_apply.py" in (BUNDLE / "main.yml").read_text(), (
        "Wire consumer before executing real bundle"
    )
    assert IMAGE.startswith("sha256:") and len(IMAGE) == 71
    name = "r42-installer-" + uuid.uuid4().hex[:12]
    root = tmp_path / "managed"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    inventory = tmp_path / "inventory"
    inventory.write_text("localhost ansible_connection=local\n")
    wrapper = tmp_path / "play.yml"
    wrapper.write_text("- import_playbook: " + str(BUNDLE / "main.yml") + "\n")
    extra = tmp_path / "vars.json"
    variables = {
        "global_vm_ssh_name": "localhost",
        "ansible_become": False,
        "BACKEND_INSTALL_ROOT": str(root),
        "BACKEND_INSTALL_NAME": name,
        "BACKEND_IMAGE": IMAGE,
        "BACKEND_UID": os.getuid(),
        "BACKEND_GID": os.getgid(),
        "API_PORT": port,
    }
    env = {
        **os.environ,
        "RANGE42_BUNDLE_DIR": str(ROOT / "bundles"),
        "ANSIBLE_NOCOLOR": "1",
    }
    binary = shutil.which("ansible-playbook")
    assert binary
    docker_config = tmp_path / "docker-config"
    docker_config.mkdir(mode=0o700)
    (docker_config / "config.json").write_text("{}")
    docker_env = {
        **os.environ,
        "DOCKER_CONFIG": str(docker_config),
        "DOCKER_BUILDKIT": "0",
    }
    containers = []
    images = []

    def run(change=None):
        extra.write_text(json.dumps({**variables, **(change or {})}))
        result = subprocess.run(
            [binary, "-i", str(inventory), str(wrapper), "-e", "@" + str(extra)],
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        return result

    def cli(*args):
        result = subprocess.run(
            ["docker", "--host", "unix:///var/run/docker.sock", *args],
            capture_output=True,
            text=True,
            timeout=30,
            env=docker_env,
        )
        assert result.returncode == 0, "Disposable Docker command failed"
        return result.stdout.strip()

    try:
        first = run()
        assert first.returncode == 0, first.stdout
        record_path = root / "installation.json"
        record = json.loads(record_path.read_text())
        assert record["status"] == "ready"
        containers.append(record["container_id"])
        assert record["image_id"] == IMAGE
        assert record["config"]["workspace_host"] == str(root / "state/workspaces")
        assert (
            record["config"]["database_container"]
            == "/var/lib/range42/workspaces/.range42.db"
        )
        assert (root / "state/workspaces/.range42.db").is_file()
        secrets = {
            name: digest(root / "secrets" / name)
            for name in ["api-token", "credential-key"]
        }
        record_before = record_path.read_bytes()
        inode = (root / "state/maintenance.lock").stat().st_ino
        database = root / "state/workspaces/.range42.db"
        sentinel = root / "state/workspaces/history-kept.jsonl"
        sentinel.write_text("preserved history\n")
        second = run()
        assert second.returncode == 0, second.stdout
        assert "unchanged" in second.stdout
        assert record_path.read_bytes() == record_before
        assert (
            json.loads(cli("inspect", record["container_id"]))[0]["State"]["Running"]
            is True
        )
        assert (root / "state/maintenance.lock").stat().st_ino == inode
        assert {name: digest(root / "secrets" / name) for name in secrets} == secrets
        assert sentinel.read_text() == "preserved history\n"
        assert database.is_file()
        rejected = run({"API_PORT": port + 1 if port < 65535 else port - 1})
        assert rejected.returncode != 0 and "guarded update" in rejected.stdout
        assert record_path.read_bytes() == record_before
        assert (
            json.loads(cli("inspect", record["container_id"]))[0]["State"]["Running"]
            is True
        )
        key = root / "secrets/credential-key"
        original = key.read_bytes()
        try:
            import base64

            key.write_bytes(base64.urlsafe_b64encode(os.urandom(32)) + b"\n")
            refused = run()
            assert refused.returncode != 0 and "credential" in refused.stdout.lower()
            assert record_path.read_bytes() == record_before
        finally:
            key.write_bytes(original)
        # The public update action must respect real provisioning work before stop.
        alternate = port + 1 if port < 65535 else port - 1
        provisioning = root / "state/workspaces/.locks/provisioning.lock"
        provisioning.parent.mkdir(mode=0o700, exist_ok=True)
        provisioning.touch(mode=0o600, exist_ok=True)
        with provisioning.open("r") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            refused = run({"BACKEND_INSTALL_ACTION": "update", "API_PORT": alternate})
            assert refused.returncode != 0
            assert (
                json.loads(cli("inspect", record["container_id"]))[0]["State"][
                    "Running"
                ]
                is True
            )
            assert record_path.read_bytes() == record_before
        updated = run({"BACKEND_INSTALL_ACTION": "update", "API_PORT": alternate})
        assert updated.returncode == 0, updated.stdout
        current = json.loads(record_path.read_text())
        containers.append(current["container_id"])
        assert current["container_id"] != record["container_id"]
        assert current["config"]["port"] == alternate
        assert (
            json.loads(cli("inspect", record["container_id"]))[0]["State"]["Running"]
            is False
        )
        assert (root / "state/maintenance.lock").stat().st_ino == inode
        assert sentinel.read_text() == "preserved history\n"
        assert {name: digest(root / "secrets" / name) for name in secrets} == secrets
        # A real failing candidate alters only its test database, then exits.
        # The installer must restore the backup before restarting the old ID.
        broken = tmp_path / "broken-image"
        broken.mkdir()
        (broken / "Dockerfile").write_text(
            "FROM "
            + IMAGE
            + '\nCOPY fail.py /tmp-fail.py\nENTRYPOINT ["python", "/tmp-fail.py"]\n'
        )
        (broken / "fail.py").write_text(
            "import os, sqlite3\n"
            'p=os.environ["RANGE42_DB_URL"].removeprefix("sqlite+aiosqlite:///")\n'
            'with sqlite3.connect(p) as db: db.execute("CREATE TABLE failed_candidate (value TEXT)")\n'
            "raise SystemExit(23)\n"
        )
        failed_image = cli("build", "--quiet", str(broken))
        images.append(failed_image)
        current_bytes = record_path.read_bytes()
        failed = run(
            {
                "BACKEND_INSTALL_ACTION": "update",
                "API_PORT": alternate,
                "BACKEND_IMAGE": failed_image,
            }
        )
        assert failed.returncode != 0 and "restored" in failed.stdout.lower(), (
            failed.stdout
        )
        assert (root / "state/maintenance.lock").read_bytes() == b''
        from test_backend_container_consumer import consumer
        assert consumer().request(current['config'], '/v1/health/ready')['ready'] is True
        assert record_path.read_bytes() == current_bytes
        assert (
            json.loads(cli("inspect", current["container_id"]))[0]["State"]["Running"]
            is True
        )
        with sqlite3.connect(database) as db:
            assert (
                db.execute(
                    "SELECT name FROM sqlite_master WHERE name='failed_candidate'"
                ).fetchall()
                == []
            )
        assert sentinel.read_text() == "preserved history\n"
        assert (root / "state/maintenance.lock").stat().st_ino == inode
    finally:
        # Recover only exact owned IDs from our uniquely named disposable project.
        found = cli(
            "ps",
            "-aq",
            "--no-trunc",
            "--filter",
            "label=org.range42.installation=" + str(root),
        )
        containers.extend(found.splitlines())
        for identifier in set(containers):
            cli("rm", "--force", identifier)
        networks = cli(
            "network",
            "ls",
            "--quiet",
            "--filter",
            "label=org.range42.installation=" + str(root),
        ).splitlines()
        for network in networks + [name + "_default"]:
            subprocess.run(
                [
                    "docker",
                    "--host",
                    "unix:///var/run/docker.sock",
                    "network",
                    "rm",
                    network,
                ],
                capture_output=True,
                timeout=15,
            )
        for image in images:
            cli("image", "rm", "--no-prune", image)
        assert cli("image", "inspect", IMAGE, "--format", "{{.Id}}") == IMAGE


def test_managed_runtime_is_staged_with_actual_profile_and_readonly_mounts(tmp_path):
    from test_backend_container_consumer import consumer

    module = consumer()
    name = "r42-installer-runtime-" + uuid.uuid4().hex[:8]
    root = tmp_path / "managed"
    runtime = tmp_path / "runtime"
    template = tmp_path / "template"
    template.mkdir(mode=0o700)
    (template / "fixture.txt").write_bytes(b"private fixture\n")
    for relative in (
        "range42-playbooks/bundles",
        "range42-ansible_roles-proxmox_controller/roles",
        "range42-catalog/02_ansible_layer/admin/roles",
        "range42-catalog/02_ansible_layer/trainee/roles",
        "range42-catalog/03_container_layer/docker/_ctf",
        "range42/roles",
        "collections",
    ):
        (runtime / relative).mkdir(parents=True, exist_ok=True)
    (runtime / "range42/roles/file").write_text("fixture\n")
    (runtime / "range42/roles/link").symlink_to("./file")
    (runtime / "ansible.cfg").write_text("[defaults]\nhost_key_checking = True\n")
    shutil.copyfile("/etc/ssl/certs/ca-certificates.crt", runtime / "proxmox-ca.pem")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = {
        "root": str(root),
        "name": name,
        "image": IMAGE,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "port": port,
        "runtime_dir": str(runtime),
        "workspace_template_dir": str(template),
    }
    plan = module.validate_config(config)
    environment = module.compose_document(plan, "a" * 32)["services"]["api"][
        "environment"
    ]
    docker = module.DockerCLI()
    args = [
        "run",
        "--rm",
        "--read-only",
        "--entrypoint",
        "python",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={runtime},dst=/runtime,readonly",
    ]
    for key, value in environment.items():
        args += ["--env", key + "=" + value]
    code = """import json
from pathlib import Path
from app.core.bundle_runtime import build_runtime_manifest
components = {name: Path('/runtime') / directory for name, directory in {
'playbooks': 'range42-playbooks', 'controller': 'range42-ansible_roles-proxmox_controller',
'catalog': 'range42-catalog', 'range42': 'range42', 'collections': 'collections',
'ansible_config': 'ansible.cfg'}.items()}
print(json.dumps(build_runtime_manifest(components)))
"""
    (runtime / "bundle-runtime.json").write_text(
        docker._run(args + [IMAGE, "-c", code], timeout=30)
    )
    try:
        assert module.apply(config)["status"] == "ready"
        record = json.loads((root / "installation.json").read_text())
        info = docker.inspect(record["container_id"])
        mounts = {row["Destination"]: row for row in info["Mounts"]}
        assert mounts["/runtime"]["RW"] is False
        assert mounts["/run/range42-template"]["RW"] is False
        assert mounts["/runtime"]["Source"] != str(runtime)
        assert (
            os.readlink(Path(mounts["/runtime"]["Source"]) / "range42/roles/link")
            == "./file"
        )
        module.verify_ready(docker, record["container_id"])
        probe = """import errno
from pathlib import Path
try: Path('/runtime/range42/roles/file').write_text('changed')
except OSError as exc: assert exc.errno == errno.EROFS
else: raise AssertionError('runtime unexpectedly writable')
print('readonly')
"""
        assert (
            docker._run(["exec", record["container_id"], "python", "-c", probe]).strip()
            == "readonly"
        )
        # Editing the operator's source never edits the active immutable runtime.
        (runtime / "range42/roles/file").write_text("changed source\n")
        with pytest.raises(ValueError, match="guarded update"):
            module.apply(config)
        assert (
            Path(mounts["/runtime"]["Source"]) / "range42/roles/file"
        ).read_text() == "fixture\n"
    finally:
        ids = docker._run(
            [
                "ps",
                "-aq",
                "--no-trunc",
                "--filter",
                "label=org.range42.installation=" + str(root),
            ]
        ).splitlines()
        for identifier in ids:
            docker._run(["rm", "--force", identifier])
        networks = docker._run(
            [
                "network",
                "ls",
                "--quiet",
                "--filter",
                "label=org.range42.installation=" + str(root),
            ]
        ).splitlines()
        for network in networks:
            docker._run(["network", "rm", network])
