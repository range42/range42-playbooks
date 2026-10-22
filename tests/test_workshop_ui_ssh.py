"""The private UI runtime retains strict authentication and bounded native SSH."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_ui_runtime_ssh_detects_disconnected_channels_without_weakening_trust(tmp_path):
    source = ROOT / 'scenarios/native_install_workshop/files/workshop_ui.py'
    spec = importlib.util.spec_from_file_location('workshop_ui_ssh', source)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    path = tmp_path / 'ansible.cfg'
    path.write_text(helper.runtime_ansible_config())
    code = '''import json
from ansible.plugins.loader import connection_loader
from ansible.playbook.play_context import PlayContext
from ansible import constants
p=connection_loader.get('ssh',PlayContext(),None);p.set_options()
print(json.dumps({'args':p.get_option('ssh_args'),'retries':p.get_option('reconnection_retries'),'strict':constants.HOST_KEY_CHECKING}))'''
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
        env={**os.environ, 'ANSIBLE_CONFIG': str(path)}, check=True)
    value = json.loads(r.stdout)
    native = subprocess.run(['ssh', '-G', '-F', '/dev/null', *shlex.split(value['args']), 'guest.invalid'],
        capture_output=True, text=True, check=True)
    options = dict(line.split(' ', 1) for line in native.stdout.splitlines())
    assert options['serveraliveinterval'] == '15'
    assert options['serveralivecountmax'] == '3'
    assert options['controlmaster'] == 'auto' and options['controlpersist'] == '60'
    assert value['retries'] == 3 and value['strict'] is True
    assert 'stricthostkeychecking' not in value['args'].lower()
    assert 'identityfile' not in value['args'].lower()
