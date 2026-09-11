"""The legacy command delegates selected names to guarded Ansible, never devkits."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios/blank_scenario_2_sdn"


def shell_fixture(tmp_path):
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    script = scenario / "scenario.delete_networks.sh"
    shutil.copyfile(SCENARIO / "blank_scenario_2_sdn.delete_networks.sh", script)
    declaration = scenario / "00_sdn_bootstrap/delete.yml"
    declaration.parent.mkdir()
    declaration.write_text("---\n[]\n")
    bins = tmp_path / "bin"
    bins.mkdir()
    receipt = tmp_path / "argv.json"
    runner = bins / "ansible-playbook"
    runner.write_text(
        f'#!{sys.executable}\nimport json,os,pathlib,sys\npathlib.Path(os.environ["CLI_RECEIPT"]).write_text(json.dumps(sys.argv[1:]))\nraise SystemExit(int(os.environ.get("CLI_RESULT", "0")))\n'
    )
    runner.chmod(0o700)
    environment = {
        **os.environ,
        "PATH": str(bins) + os.pathsep + os.environ["PATH"],
        "CLI_RECEIPT": str(receipt),
        "RANGE42_ANSIBLE_ROLES__INVENTORY_DIR": str(tmp_path),
        "RANGE42_VAULT_PASSWORD_FILE": str(tmp_path / "vault-password"),
    }
    return script, receipt, environment


@pytest.mark.parametrize("flag", ["--dry-run", "--check", "-C"])
def test_cli_read_only_uses_guarded_bundle_preview_without_ansible_check_skips(
    tmp_path, flag
):
    script, receipt, environment = shell_fixture(tmp_path)
    result = subprocess.run(
        ["bash", str(script), flag, "-vv"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    args = json.loads(receipt.read_text())
    assert str(script.parent / "00_sdn_bootstrap/delete.yml") in args
    assert "-vv" in args
    assert flag not in args
    assert json.loads(args[-1]) == {"BUNDLE_SDN_DELETE_READ_ONLY": True}


def test_cli_preserves_arguments_and_ansible_failure(tmp_path):
    script, receipt, environment = shell_fixture(tmp_path)
    environment["CLI_RESULT"] = "19"
    result = subprocess.run(
        ["bash", str(script), "-vv"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 19, result.stderr
    args = json.loads(receipt.read_text())
    assert args[-1] == "-vv"
    assert "--vault-password-file" in args


def test_actual_legacy_cli_consumes_manifest_and_executes_guarded_read_only_flow(
    tmp_path, monkeypatch
):
    import yaml
    from test_sdn_delete_all import paired

    initial, observed, _ = paired(tmp_path, monkeypatch, selected=True, read_only=True)
    assert initial.returncode == 0, initial.stdout[-7000:] + initial.stderr
    scenario = tmp_path / "cli-scenario"
    (scenario / "00_sdn_bootstrap").mkdir(parents=True)
    (scenario / "manifest").mkdir()
    script = scenario / "scenario.delete_networks.sh"
    shutil.copyfile(SCENARIO / "blank_scenario_2_sdn.delete_networks.sh", script)
    shutil.copyfile(
        SCENARIO / "00_sdn_bootstrap/delete.yml",
        scenario / "00_sdn_bootstrap/delete.yml",
    )
    (scenario / "manifest/scenario_vms.json").write_text(
        json.dumps(
            {
                "vms": [{"bridge": "net1"}, {"bridge": "vmbr140", "ip": "10.42.70.55"}],
                "templates": [{"bridge": "net1"}],
            }
        )
    )
    config = tmp_path / "config"
    (config / "secrets").mkdir()
    variables = yaml.safe_load((tmp_path / "playbook.yml").read_text())[0]["vars"]
    variables["range42_sdn_zone"] = "lab"
    vault = config / "secrets/default_vault.yml"
    vault.write_text(yaml.safe_dump(variables))
    vault.chmod(0o600)
    password = tmp_path / "fixture-vault-password"
    password.write_text("fixture-only\n")
    password.chmod(0o600)
    shutil.copyfile(tmp_path / "hosts.yml", tmp_path / "inventory_default.yml")
    result = subprocess.run(
        ["bash", str(script), "--dry-run"],
        env={
            **os.environ,
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
            "ANSIBLE_ROLES_PATH": str(tmp_path / "roles"),
            "ANSIBLE_LIBRARY": str(tmp_path / "library"),
            "ANSIBLE_NOCOLOR": "1",
            "RANGE42_BUNDLE_DIR": str(ROOT / "bundles"),
            "RANGE42_ANSIBLE_ROLES__INVENTORY_DIR": str(tmp_path),
            "RANGE42_VAULT_PASSWORD_FILE": str(password),
        },
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout[-8000:] + result.stderr
    assert "REPORT READ-ONLY DECLARATION SCOPE" in result.stdout
    assert "net1" in result.stdout and "lab" in result.stdout
    assert not (config / ".sdn-delete").exists()
    assert not (tmp_path / "deletions.json").exists()
    assert not Path(observed["apply_marker"]).exists()
    assert all(
        json.loads(Path(node["writes"]).read_text()) == []
        for node in observed["nodes"].values()
    )
