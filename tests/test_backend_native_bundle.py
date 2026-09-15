"""Actual local Ansible consumer boundary; no Docker, services or credentials.

The recording consumer replaces only the out-of-scope mutation engine. The real
bundle and native app callsite must validate inputs and transport exact JSON.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundles/admin/software.install.deployer_api_backend"
CALLSITE = (
    ROOT
    / "scenarios/dev_deployer_ui_lab/02_dev_deployer_ui_lab_infrastructure/stage_01-vm_configure/dev-backend.yml"
)
IMAGE = "sha256:" + "a" * 64


@pytest.fixture
def run_bundle(tmp_path):
    bundle_root = tmp_path / "bundles"
    bundle = bundle_root / "admin/software.install.deployer_api_backend"
    (bundle / "files").mkdir(parents=True)
    shutil.copyfile(BUNDLE / "main.yml", bundle / "main.yml")
    capture = tmp_path / "captured.json"
    (bundle / "files/container_apply.py").write_text(
        "import json, pathlib, sys\n"
        f"path = pathlib.Path({str(capture)!r})\n"
        "with path.open('x') as stream: json.dump(json.load(sys.stdin), stream)\n"
        "print(json.dumps({'status': 'recorded', 'changed': False}))\n"
    )
    inventory = tmp_path / "inventory"
    inventory.write_text("localhost ansible_connection=local\n")
    play = tmp_path / "play.yml"
    config = tmp_path / "ansible.cfg"
    config.write_text(
        "[defaults]\nretry_files_enabled = False\nhost_key_checking = True\n"
    )
    binary = Path(sys.executable).with_name("ansible-playbook")
    assert binary.is_file(), "Use the backend Python environment with Ansible installed"

    def run(extra=None, *, callsite=False):
        if callsite:
            shutil.copyfile(CALLSITE, play)
        else:
            play.write_text("- import_playbook: " + str(bundle / "main.yml") + "\n")
        variables = {
            "global_vm_ssh_name": "localhost",
            "ansible_become": False,
            "ansible_python_interpreter": sys.executable,
            "BACKEND_IMAGE": IMAGE,
            **(extra or {}),
        }
        extra_file = tmp_path / "vars.json"
        extra_file.write_text(json.dumps(variables))
        result = subprocess.run(
            [str(binary), "-i", str(inventory), str(play), "-e", "@" + str(extra_file)],
            cwd=tmp_path,
            env={
                "PATH": os.environ["PATH"],
                "HOME": str(tmp_path),
                "LANG": "C.UTF-8",
                "ANSIBLE_CONFIG": str(config),
                "ANSIBLE_NOCOLOR": "1",
                "RANGE42_BUNDLE_DIR": str(bundle_root),
            },
            capture_output=True,
            text=True,
            timeout=40,
        )
        value = json.loads(capture.read_text()) if capture.exists() else None
        return result, value

    return run


@pytest.mark.parametrize("action", [None, "apply", "fresh", "update"])
def test_existing_actions_retain_exact_two_key_stdin(run_bundle, action):
    result, value = run_bundle({"BACKEND_INSTALL_ACTION": action} if action else {})
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(value) == {"config", "operation"}
    assert value["operation"] == (action or "apply")
    assert value["config"]["image"] == IMAGE


def test_adoption_transports_only_private_target_file_reference(run_bundle, tmp_path):
    proof = tmp_path / "private-adoption.json"
    proof.write_text('{"never_export": "PRIVATE_PROOF_CONTENT"}')
    original = proof.read_bytes()
    result, value = run_bundle(
        {
            "BACKEND_INSTALL_ACTION": "adopt-systemd",
            "BACKEND_SYSTEMD_ADOPTION_FILE": str(proof),
        }
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert set(value) == {"config", "operation", "adoption_file"}
    assert value["adoption_file"] == str(proof)
    assert "adoption_file" not in value["config"]
    assert proof.read_bytes() == original
    assert str(proof) not in result.stdout + result.stderr
    assert "PRIVATE_PROOF_CONTENT" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "extra",
    [
        {"BACKEND_INSTALL_ACTION": "adopt-systemd"},
        {
            "BACKEND_INSTALL_ACTION": "adopt-systemd",
            "BACKEND_SYSTEMD_ADOPTION_FILE": "",
        },
        {
            "BACKEND_INSTALL_ACTION": "adopt-systemd",
            "BACKEND_SYSTEMD_ADOPTION_FILE": "relative.json",
        },
        {
            "BACKEND_INSTALL_ACTION": "adopt-systemd",
            "BACKEND_SYSTEMD_ADOPTION_FILE": {"inline": "unsupported"},
        },
        {
            "BACKEND_INSTALL_ACTION": "apply",
            "BACKEND_SYSTEMD_ADOPTION_FILE": "/private/proof.json",
        },
        {"BACKEND_INSTALL_ACTION": "unreviewed"},
    ],
)
def test_invalid_action_or_adoption_binding_refuses_before_consumer(run_bundle, extra):
    result, value = run_bundle(extra)
    assert result.returncode != 0
    assert value is None, "Invalid adoption must not reach a mutating consumer"


def test_explicit_native_runtime_and_network_bindings_reach_planner(run_bundle):
    bindings = {
        "runtime_container": "/opt/range42",
        "runtime_config_container": "/etc/range42",
        "runtime_ca_container": "/etc/range42/proxmox-ca.pem",
        "workspace_template_container": "/etc/range42/workspace-template",
        "inventory_container": "/var/lib/range42/inventory",
        "network_mode": "host",
    }
    result, value = run_bundle(
        {"BACKEND_" + key.upper(): item for key, item in bindings.items()}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert {key: value["config"].get(key) for key in bindings} == bindings


def test_native_callsite_supplies_exact_lab_and_shared_origins(run_bundle):
    result, value = run_bundle(callsite=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert value["config"]["cors_origins"] == [
        "http://r42.dev-deployer-ui:3000",
        "http://192.168.142.190:3000",
        "http://100.64.0.14:3002",
    ]
    assert value["config"]["image"] == IMAGE


def test_native_cors_override_replaces_defaults_exactly(run_bundle):
    origins = ["https://reviewed.example:8443"]
    result, value = run_bundle({"BACKEND_CORS_ORIGINS": origins}, callsite=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert value["config"]["cors_origins"] == origins


def test_descriptor_exposes_typed_adoption_and_native_bindings():
    source = yaml.safe_load((BUNDLE / "bundle_parameters.src.yml").read_text())
    generated = json.loads((BUNDLE / "bundle_parameters.json").read_text())
    assert generated["params"] == source["params"]
    params = {entry["name"]: entry for entry in generated["params"]}
    assert params["BACKEND_INSTALL_ACTION"]["allowed"] == [
        "apply",
        "fresh",
        "update",
        "adopt-systemd",
    ]
    for name in (
        "BACKEND_SYSTEMD_ADOPTION_FILE",
        "BACKEND_RUNTIME_CONTAINER",
        "BACKEND_RUNTIME_CONFIG_CONTAINER",
        "BACKEND_RUNTIME_CA_CONTAINER",
        "BACKEND_WORKSPACE_TEMPLATE_CONTAINER",
        "BACKEND_INVENTORY_CONTAINER",
        "BACKEND_NETWORK_MODE",
    ):
        assert params[name]["type"] == "string"
        assert params[name]["required"] is False
    assert params["BACKEND_NETWORK_MODE"]["allowed"] == ["bridge", "host"]
    assert params["BACKEND_CORS_ORIGINS"]["type"] == "list"
    assert params["BACKEND_GIT_ALLOWED_HOSTS"]["type"] == "list"
