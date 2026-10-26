"""Render the actual native bundle inputs against application-owned Compose."""
import copy
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundles/admin/software.install.deployer_api_backend"
API = Path(os.getenv("RANGE42_BACKEND_SOURCE", str(ROOT.parent / "range42-backend-api")))


@pytest.fixture
def rendered(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    plays = yaml.safe_load((BUNDLE / "main.yml").read_text())
    play = next(p for p in plays if any(t.get("name", "").startswith("Render .env") for t in p.get("tasks", [])))
    tasks = [copy.deepcopy(t) for t in play["tasks"] if t.get("name", "").startswith(
        ("Render .env", "Render docker-compose.override"))]
    for task in tasks:
        module = task["ansible.builtin.copy"]
        module.pop("owner", None)
        module.pop("group", None)
    variables = {**play.get("vars", {}), "REMOTE_PROJECT_DIR": str(project), "API_PORT": 18001,
        "BACKEND_LISTEN_ADDRESS": "0.0.0.0", "API_CONTAINER_UID": os.getuid(), "API_CONTAINER_GID": os.getgid(),
        "API_SECRETS_DIR_HOST": str(tmp_path / "credentials"), "API_STATE_DIR_HOST": str(tmp_path / "state"),
        "API_HOME_DIR_HOST": str(tmp_path / "home"), "WORKSPACE_DIR_HOST": str(tmp_path / "workspaces"),
        "RUNTIME_DIR_HOST": str(tmp_path / "runtime"), "WORKSPACE_TEMPLATE_DIR_HOST": str(tmp_path / "template"),
        "BACKEND_CORS_ORIGINS": "https://staff.example.test", "DEPLOYER_UI_CORS_REGEX": "^https://staff\\.example\\.test$"}
    fixture = tmp_path / "render.yml"
    fixture.write_text(yaml.safe_dump([{"hosts": "localhost", "connection": "local", "gather_facts": False,
                                      "vars": variables, "tasks": tasks}], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nhost_key_checking = True\n")
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(fixture)],
        env={**os.environ, "ANSIBLE_CONFIG": str(config)}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    for filename in ("docker-compose.yml", "docker-compose.runtime.yml"):
        (project / filename).write_text((API / filename).read_text())
    command = ["docker", "compose", "--project-directory", str(project), "-p", "native-bundle-render",
        "-f", str(project / "docker-compose.yml"), "-f", str(project / "docker-compose.runtime.yml"),
        "-f", str(project / "docker-compose.override.yml"), "config", "--format", "json"]
    # Empty directories are sufficient for config; no container or image is started.
    env = {**os.environ, "RANGE42_RUNTIME_DIR": variables["RUNTIME_DIR_HOST"],
           "RANGE42_WORKSPACE_TEMPLATE_DIR": variables["WORKSPACE_TEMPLATE_DIR_HOST"]}
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout), variables


def test_native_port_uid_and_cors_reach_packaged_compose(rendered):
    compose, values = rendered
    api = compose["services"]["api"]
    assert api["ports"][0]["published"] == str(values["API_PORT"])
    assert api["ports"][0]["host_ip"] == values["BACKEND_LISTEN_ADDRESS"]
    assert api["build"]["args"]["APP_UID"] == str(values["API_CONTAINER_UID"])
    assert api["environment"]["RANGE42_CORS_ORIGINS"] == values["BACKEND_CORS_ORIGINS"]
    # Compose config serializes a literal dollar as $$ for round-tripping.
    assert api["environment"]["CORS_ORIGIN_REGEX"].replace("$$", "$") == values["DEPLOYER_UI_CORS_REGEX"]


def test_native_secrets_and_persistent_workspace_are_selected(rendered):
    compose, values = rendered
    assert compose["secrets"]["api_token"]["file"] == values["API_SECRETS_DIR_HOST"] + "/api-token"
    assert compose["secrets"]["credential_key"]["file"] == values["API_SECRETS_DIR_HOST"] + "/credential-key"
    api = compose["services"]["api"]
    assert api["environment"]["HOME"] == "/home/range42"
    assert api["environment"]["RANGE42_WORKSPACE_ROOT"] == "/home/range42/range42.config"
    mounts = {item["target"]: item for item in api["volumes"]}
    assert mounts["/var/lib/range42"]["source"] == values["API_STATE_DIR_HOST"]
    assert mounts["/home/range42/range42.config"]["source"] == values["WORKSPACE_DIR_HOST"]
    assert api["environment"]["RANGE42_CONTEXT_ROOT"] == "/home/range42/range42.config"
    assert mounts["/runtime"]["read_only"] is True
    assert mounts["/run/range42-template"]["read_only"] is True


def test_registration_uses_bearer_without_publishing_credentials():
    plays = yaml.safe_load((BUNDLE / "main.yml").read_text())
    seed = next(t for p in plays for t in p.get("tasks", []) if t.get("name", "").startswith("Register Proxmox host"))
    assert seed.get("no_log") is True
    assert "Bearer" in seed["ansible.builtin.uri"].get("headers", {}).get("Authorization", "")


def test_public_liveness_replaces_unauthenticated_openapi_probe():
    plays = yaml.safe_load((BUNDLE / "main.yml").read_text())
    probes = [t["ansible.builtin.uri"] for p in plays for t in p.get("tasks", []) if "ansible.builtin.uri" in t]
    assert any(p["url"].endswith("/v1/health") for p in probes)
    assert not any(p["url"].endswith("/docs/openapi.json") for p in probes)
    ready = next(p for p in probes if p["url"].endswith("/v1/health/ready"))
    assert "Bearer" in ready["headers"]["Authorization"]


def test_native_installer_records_explicit_registered_target_and_refuses_retargeting(tmp_path):
    plays = yaml.safe_load((BUNDLE / 'main.yml').read_text())
    tasks = [copy.deepcopy(t) for p in plays for t in p.get('tasks', [])
             if t.get('name', '').startswith(('Inspect native target binding', 'Read native target binding',
                 'Require unchanged native target binding', 'Record registered native target binding'))]
    assert len(tasks) == 4, 'Native installation must pin its registered target without manual registry editing'
    for task in tasks:
        if 'ansible.builtin.copy' in task:
            task['ansible.builtin.copy'].pop('owner', None)
            task['ansible.builtin.copy'].pop('group', None)
    workspace = tmp_path / 'workspaces' / 'training-demo';workspace.mkdir(parents=True)
    config = tmp_path / 'ansible.cfg';config.write_text('[defaults]\nhost_key_checking = True\n')
    def run(node):
        variables = {'WORKSPACE_DIR_HOST_RESOLVED': str(workspace.parent), 'WORKSPACE_DIR_NAME': workspace.name,
            'CONTAINER_UID': os.getuid(), 'CONTAINER_GID': os.getgid(),
            'native_target_binding': {'version': 1, 'target_host_id': 'registered-host', 'target_node': node, 'target_api_url': 'https://pve.example.test:8006'},
            'register_proxmox_result': {'json': {'id': 'registered-host', 'node_name': node,
                'api_url': 'https://pve.example.test:8006'}}}
        play = tmp_path / 'binding.yml';play.write_text(yaml.safe_dump([{'hosts': 'localhost',
            'connection': 'local', 'gather_facts': False, 'vars': variables, 'tasks': tasks}], sort_keys=False))
        return subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)],
            env={**os.environ, 'ANSIBLE_CONFIG': str(config)}, capture_output=True, text=True, timeout=30)
    first = run('pve-a');assert first.returncode == 0, first.stdout + first.stderr
    path = workspace / '.range42-target.json';before = path.read_bytes()
    assert json.loads(before) == {'version': 1, 'target_host_id': 'registered-host',
        'target_node': 'pve-a', 'target_api_url': 'https://pve.example.test:8006'}
    assert path.stat().st_mode & 0o777 == 0o600
    repeat = run('pve-a');assert repeat.returncode == 0, repeat.stdout + repeat.stderr
    assert path.read_bytes() == before
    drift = run('pve-b');assert drift.returncode != 0
    assert path.read_bytes() == before
