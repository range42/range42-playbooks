"""The public CLI recipe must preserve explicit Ansible recovery arguments."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['catalog_try.setup.sh', 'catalog_try.setup_vms_only.sh'])
def test_catalog_try_recipe_forwards_recovery_arguments_without_interpreting_them(tmp_path, name):
    capture = tmp_path / 'argv.json'
    binary = tmp_path / 'ansible-playbook'
    binary.write_text(f'#!{sys.executable}\nimport sys,json\nfrom pathlib import Path\nPath({str(capture)!r}).write_text(json.dumps(sys.argv[1:]))\n')
    binary.chmod(0o700)
    marker = tmp_path / 'must-not-exist'
    task = 'native readiness; touch ' + str(marker)
    arguments = ['--start-at-task', task, '-e', 'selected=fixed value']
    result = subprocess.run(['bash', str(ROOT / 'scenarios/catalog_try' / name), *arguments],
        env={**os.environ, 'PATH': str(tmp_path) + ':' + os.environ['PATH'],
             'RANGE42_ANSIBLE_ROLES__INVENTORY_DIR': '/private/inventory',
             'RANGE42_VAULT_PASSWORD_FILE': '/private/vault-pass'}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(capture.read_text())[-len(arguments):] == arguments
    assert not marker.exists()
