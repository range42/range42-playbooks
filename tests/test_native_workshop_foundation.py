"""The optional foundation remains a catalog scenario using the native attempt."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT/'scenarios/native_workshop_foundation'


def test_foundation_declares_no_fixed_participant_ids_networks_or_identity_provider():
    assert (SCENARIO/'manifest/preparation.json').is_file(), 'Missing reusable foundation catalog scenario'
    declared = json.loads((SCENARIO/'manifest/preparation.json').read_text())
    assert declared == {'version': 1, 'kind': 'native-workshop-foundation', 'title': 'Prepare reusable workshop templates'}
    manifest = json.loads((SCENARIO/'manifest/scenario_vms.json').read_text())
    assert manifest['vms'] == [] and manifest['templates'] == []
    runtime = json.loads((SCENARIO/'manifest/scenario_runtime.json').read_text())
    assert runtime['actions'] == {'full': 'main.yml'}
    entry = (SCENARIO/'main.yml').read_text()
    assert 'headscale' not in entry.lower() and 'keycloak' not in entry.lower()
    assert 'pvesh' not in entry and 'qm ' not in entry and 'curl' not in entry
    assert 'ansible.builtin.command' in entry


def test_real_ansible_hands_the_private_request_to_the_fixed_backend_adapter(tmp_path):
    assert (SCENARIO/'main.yml').is_file(), 'Missing canonical foundation entrypoint'
    executable = shutil.which('ansible-playbook')
    if not executable:
        pytest.skip('Ansible is unavailable')
    runner = tmp_path/'fixture.py'
    runner.write_text('''import json,sys
assert sys.argv[1:] == ['--request-file', sys.argv[2], '--target-host-id', 'selected-host', '--agent-revision', 'f'*64]
request=json.load(open(sys.argv[2]))
assert request == {'original': True}
print(json.dumps({'status':'complete','request_id':'a'*32,'foundation_ready':True,'changed':True}))
''')
    request = tmp_path/'request.json'
    request.write_text('{"original":true}')
    request.chmod(0o600)
    variables = tmp_path/'variables.json'
    variables.write_text(json.dumps({'range42_foundation_python': sys.executable,
        'range42_foundation_runner_file': str(runner), 'range42_foundation_request_file': str(request),
        'range42_foundation_target_host_id': 'selected-host', 'range42_foundation_agent_revision': 'f'*64}))
    result = subprocess.run([executable, '-i', 'localhost,', '-c', 'local', str(SCENARIO/'main.yml'),
        '--extra-vars', '@'+str(variables)], cwd=ROOT, env={**os.environ, 'ANSIBLE_NOCOLOR': '1'},
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'failed=0' in result.stdout
    assert request.read_text() == '{"original":true}'
    assert all('hosts' in play for play in yaml.safe_load((SCENARIO/'main.yml').read_text()))
