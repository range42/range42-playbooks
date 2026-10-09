"""Opt-in native context/scenario acceptance against disposable local Docker services.

This tests the application stages. Proxmox VM/template/network creation is skipped.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import uuid
import urllib.error
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not os.getenv("RANGE42_CONTEXT_BOOTSTRAP_ACCEPTANCE"),
                                reason="opt-in Docker/native CLI application acceptance")


def test_native_scenario_builds_backend_without_image_input_and_preserves_repeat_state(tmp_path):
    core = Path(os.environ["RANGE42_CLI_TEST_SOURCE"])
    api = Path(os.environ["RANGE42_API_TEST_SOURCE"])
    cli = core / "roles/deployer.bootstrap/files/range42-context.sh"
    workspace = tmp_path / "acceptance-dev_deployer_ui_lab"
    inventory = workspace / "inventory"
    inventory.mkdir(parents=True)
    (workspace / "scenario").symlink_to(ROOT / "scenarios/dev_deployer_ui_lab")
    (workspace / "secrets").mkdir(mode=0o700)
    (workspace / "secrets/vault_pass.txt").write_text("disposable-test-password")
    (workspace / "secrets/default_vault.yml").write_text("{}\n")
    (inventory / "inventory_default.yml").write_text(
        "all:\n  hosts:\n    r42.dev-backend:\n      ansible_connection: local\n")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    installation = tmp_path / "backend"
    name = "r42-context-test-" + uuid.uuid4().hex[:12]
    settings = {"ansible_become": False, "ansible_python_interpreter": shutil.which("python3"),
                "BACKEND_INSTALL_ROOT": str(installation), "BACKEND_INSTALL_NAME": name,
                "BACKEND_SOURCE_DIR": str(tmp_path / "source"), "LOCAL_CODE_PATH": str(api),
                "BACKEND_UID": os.getuid(), "BACKEND_GID": os.getgid(), "API_PORT": port,
                "BACKEND_LISTEN_ADDRESS": "127.0.0.1", "BACKEND_CORS_ORIGINS": []}
    # These are disposable host bindings, deliberately without BACKEND_IMAGE.
    (workspace / "deployment.yml").write_text(json.dumps(settings))
    roles = ":".join([str(core / "roles"),
                      str(core.parent / "range42-ansible_roles-proxmox_controller/roles"),
                      str(core.parent / "range42-catalog/02_ansible_layer/admin/roles"),
                      str(core.parent / "range42-catalog/02_ansible_layer/trainee/roles")])
    env = {**os.environ, "RANGE42_ACTIVE_CONFIG_DIR": str(workspace),
           "RANGE42_ACTIVE_WORKSPACE": workspace.name, "RANGE42_CONFIG_BASE_DIR": str(tmp_path),
           "RANGE42_ANSIBLE_ROLES__INVENTORY_DIR": str(inventory),
           "RANGE42_VAULT_PASSWORD_FILE": str(workspace / "secrets/vault_pass.txt"),
           "RANGE42_BUNDLE_DIR": str(ROOT / "bundles"), "ANSIBLE_ROLES_PATH": roles,
           "ANSIBLE_CONFIG": str(core / "ansible.cfg"), "ANSIBLE_NOCOLOR": "1"}
    command = ["zsh", "-f", "-c", 'source "$1"; _r42_flush_known_hosts() { return 0; }; '
               'range42-context deploy --limit r42.dev-backend '
               '--start-at-task "BACKEND INSTALL - Validate deployment inputs"', "acceptance", str(cli)]

    def deploy():
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=1200)
        assert result.returncode == 0, result.stdout[-9000:] + result.stderr[-2000:]
        return result

    def get(path, token=None):
        request = urllib.request.Request(f"http://127.0.0.1:{port}" + path,
                    headers={"Authorization": "Bearer " + token} if token else {})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    try:
        deploy()
        record_path = installation / "installation.json"
        record_before = record_path.read_bytes()
        record = json.loads(record_before)
        assert record["image_id"].startswith("sha256:")
        secrets = Path(record["config"]["secrets_dir"])
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in secrets.iterdir()}
        token = (secrets / "api-token").read_text().strip()
        assert get("/v1/health")["status"] == "ok"
        with pytest.raises(urllib.error.HTTPError) as error:
            get("/v1/health/ready")
        assert error.value.code == 401
        assert get("/v1/health/ready", token)["ready"] is True
        history = Path(record["config"]["workspace_host"]) / "history-kept.jsonl"
        history.write_text("must survive redeploy\n")
        second = deploy()
        assert "Backend container unchanged" in second.stdout
        assert record_path.read_bytes() == record_before
        assert history.read_text() == "must survive redeploy\n"
        assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in secrets.iterdir()} == hashes
    finally:
        # Remove only containers recorded under this test's own installation.
        record_path = installation / "installation.json"
        if record_path.is_file():
            record = json.loads(record_path.read_text())
            subprocess.run(["docker", "compose", "-f", record["release_dir"] + "/compose.json", "down"],
                           capture_output=True, timeout=30)


def test_native_scenario_builds_ui_with_the_node_selected_during_workspace_setup(tmp_path):
    core = Path(os.environ["RANGE42_CLI_TEST_SOURCE"])
    ui = Path(os.environ["RANGE42_UI_TEST_SOURCE"])
    workspace = tmp_path / "acceptance-dev_deployer_ui_lab"
    inventory = workspace / "inventory"
    inventory.mkdir(parents=True)
    (workspace / "scenario").symlink_to(ROOT / "scenarios/dev_deployer_ui_lab")
    (workspace / "secrets").mkdir(mode=0o700)
    (workspace / "secrets/vault_pass.txt").write_text("disposable-test-password")
    (workspace / "secrets/default_vault.yml").write_text("proxmox_node: showcase-node\n")
    (inventory / "inventory_default.yml").write_text(
        "all:\n  hosts:\n    r42.dev-deployer-ui:\n      ansible_connection: local\n")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    project = tmp_path / "ui-source"
    name = "r42-ui-context-" + uuid.uuid4().hex[:12]
    settings = {"ansible_become": False, "ansible_python_interpreter": shutil.which("python3"),
                "LOCAL_CODE_PATH": str(ui) + "/", "REMOTE_PROJECT_DIR": str(project),
                "UI_PORT": port, "BACKEND_API_URL": "http://192.0.2.10:18000",
                "UI_INSTALL_OWNER": os.getuid(), "UI_INSTALL_GROUP": os.getgid(),
                "UI_PROVENANCE_DIR": str(tmp_path / "provenance")}
    (workspace / "deployment.yml").write_text(json.dumps(settings))
    roles = ":".join([str(core / "roles"),
                      str(core.parent / "range42-ansible_roles-proxmox_controller/roles"),
                      str(core.parent / "range42-catalog/02_ansible_layer/admin/roles"),
                      str(core.parent / "range42-catalog/02_ansible_layer/trainee/roles")])
    env = {**os.environ, "RANGE42_ACTIVE_CONFIG_DIR": str(workspace),
           "RANGE42_ACTIVE_WORKSPACE": workspace.name, "RANGE42_CONFIG_BASE_DIR": str(tmp_path),
           "RANGE42_ANSIBLE_ROLES__INVENTORY_DIR": str(inventory),
           "RANGE42_VAULT_PASSWORD_FILE": str(workspace / "secrets/vault_pass.txt"),
           "RANGE42_BUNDLE_DIR": str(ROOT / "bundles"), "ANSIBLE_ROLES_PATH": roles,
           "ANSIBLE_CONFIG": str(core / "ansible.cfg"), "ANSIBLE_NOCOLOR": "1",
           "COMPOSE_PROJECT_NAME": name, "BUILDX_NO_DEFAULT_ATTESTATIONS": "1"}
    command = ["zsh", "-f", "-c", 'source "$1"; _r42_flush_known_hosts() { return 0; }; '
               'range42-context deploy --limit r42.dev-deployer-ui '
               '--start-at-task "Install rsync on remote (required for synchronize)"',
               "acceptance", str(core / "roles/deployer.bootstrap/files/range42-context.sh")]
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=1200)
        assert result.returncode == 0, result.stdout[-7000:] + result.stderr[-2000:]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/config.json", timeout=5) as response:
            assert json.load(response) == {"defaultBackendUrl": settings["BACKEND_API_URL"],
                                           "defaultNodeName": "showcase-node"}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            assert response.status == 200
    finally:
        if (project / "docker-compose.yml").is_file():
            subprocess.run(["docker", "compose", "down"], cwd=project, env=env,
                           capture_output=True, timeout=30)
