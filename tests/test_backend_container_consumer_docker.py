"""Opt-in actual Ansible bundle → disposable local Docker fresh/repeat acceptance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'bundles/admin/software.install.deployer_api_backend'
IMAGE = os.environ.get('RANGE42_INSTALLER_MAINTENANCE_TEST_IMAGE')
pytestmark = pytest.mark.skipif(not IMAGE, reason='requires explicit immutable local acceptance image')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_ansible_fresh_repeat_and_changed_managed_state_refusal(tmp_path):
    assert 'container_apply.py' in (BUNDLE / 'main.yml').read_text(), 'Wire consumer before executing real bundle'
    assert IMAGE.startswith('sha256:') and len(IMAGE) == 71
    name = 'r42-installer-' + uuid.uuid4().hex[:12]
    root = tmp_path / 'managed'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    inventory = tmp_path / 'inventory'
    inventory.write_text('localhost ansible_connection=local\n')
    wrapper = tmp_path / 'play.yml'
    wrapper.write_text('- import_playbook: ' + str(BUNDLE / 'main.yml') + '\n')
    extra = tmp_path / 'vars.json'
    variables = {'global_vm_ssh_name': 'localhost', 'ansible_become': False,
                 'BACKEND_INSTALL_ROOT': str(root), 'BACKEND_INSTALL_NAME': name,
                 'BACKEND_IMAGE': IMAGE, 'BACKEND_UID': os.getuid(), 'BACKEND_GID': os.getgid(),
                 'API_PORT': port}
    env = {**os.environ, 'RANGE42_BUNDLE_DIR': str(ROOT / 'bundles'), 'ANSIBLE_NOCOLOR': '1'}
    binary = shutil.which('ansible-playbook')
    assert binary
    containers = []

    def run(change=None):
        extra.write_text(json.dumps({**variables, **(change or {})}))
        result = subprocess.run([binary, '-i', str(inventory), str(wrapper), '-e', '@' + str(extra)],
                                env=env, capture_output=True, text=True, timeout=90)
        return result

    def cli(*args):
        result = subprocess.run(['docker', '--host', 'unix:///var/run/docker.sock', *args],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, 'Disposable Docker command failed'
        return result.stdout.strip()

    try:
        first = run()
        assert first.returncode == 0, first.stdout
        record_path = root / 'installation.json'
        record = json.loads(record_path.read_text())
        assert record['status'] == 'ready'
        containers.append(record['container_id'])
        assert record['image_id'] == IMAGE
        assert record['config']['workspace_host'] == str(root / 'state/workspaces')
        assert record['config']['database_container'] == '/var/lib/range42/workspaces/.range42.db'
        assert (root / 'state/workspaces/.range42.db').is_file()
        secrets = {name: digest(root / 'secrets' / name) for name in ['api-token', 'credential-key']}
        record_before = record_path.read_bytes()
        inode = (root / 'state/maintenance.lock').stat().st_ino
        database = root / 'state/workspaces/.range42.db'
        sentinel = root / 'state/workspaces/history-kept.jsonl'
        sentinel.write_text('preserved history\n')
        second = run()
        assert second.returncode == 0, second.stdout
        assert 'unchanged' in second.stdout
        assert record_path.read_bytes() == record_before
        assert json.loads(cli('inspect', record['container_id']))[0]['State']['Running'] is True
        assert (root / 'state/maintenance.lock').stat().st_ino == inode
        assert {name: digest(root / 'secrets' / name) for name in secrets} == secrets
        assert sentinel.read_text() == 'preserved history\n'
        assert database.is_file()
        rejected = run({'API_PORT': port + 1 if port < 65535 else port - 1})
        assert rejected.returncode != 0 and 'guarded update' in rejected.stdout
        assert record_path.read_bytes() == record_before
        assert json.loads(cli('inspect', record['container_id']))[0]['State']['Running'] is True
        key = root / 'secrets/credential-key'
        original = key.read_bytes()
        try:
            import base64
            key.write_bytes(base64.urlsafe_b64encode(os.urandom(32)) + b'\n')
            refused = run()
            assert refused.returncode != 0 and 'credential' in refused.stdout.lower()
            assert record_path.read_bytes() == record_before
        finally:
            key.write_bytes(original)
    finally:
        # Recover only exact owned IDs from our uniquely named disposable project.
        found = cli('ps', '-aq', '--no-trunc', '--filter', 'label=org.range42.installation=' + str(root))
        containers.extend(found.splitlines())
        for identifier in set(containers):
            cli('rm', '--force', identifier)
        network = name + '_default'
        subprocess.run(['docker', '--host', 'unix:///var/run/docker.sock', 'network', 'rm', network],
                       capture_output=True, timeout=15)
