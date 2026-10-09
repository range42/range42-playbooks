"""The native wrapper keeps private machine settings in the selected workspace."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scenarios/dev_deployer_ui_lab/dev_deployer_ui_lab.setup.sh"


def test_native_wrapper_loads_workspace_settings_before_explicit_cli_overrides(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    executable = binary / "ansible-playbook"
    executable.write_text("#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    executable.chmod(0o700)
    workspace = tmp_path / "selected context"
    workspace.mkdir()
    settings = workspace / "deployment.yml"
    settings.write_text("BACKEND_INSTALL_ROOT: /var/lib/existing-backend\n")
    result = subprocess.run(["bash", str(WRAPPER), "-e", "API_PORT=18001"], capture_output=True,
                            text=True, env={**os.environ, "PATH": str(binary) + ":" + os.environ["PATH"],
                            "RANGE42_BUNDLE_DIR": str(ROOT / "bundles"),
                            "RANGE42_ACTIVE_CONFIG_DIR": str(workspace),
                            "RANGE42_ANSIBLE_ROLES__INVENTORY_DIR": str(workspace / "inventory"),
                            "RANGE42_VAULT_PASSWORD_FILE": str(workspace / "secrets/vault_pass.txt")})
    assert result.returncode == 0, result.stderr
    arguments = json.loads(result.stdout)
    assert "@" + str(settings) in arguments, "Bare context deploy must honor its workspace's deployment settings"
    assert arguments.index("@" + str(settings)) < arguments.index("API_PORT=18001")
