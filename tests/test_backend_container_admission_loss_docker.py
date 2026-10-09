"""Actual disposable API stays fenced when installer Docker recovery fails."""
import json
import os
import socket
import time
import urllib.error
import urllib.request
import uuid

import pytest

from test_backend_container_consumer import consumer

IMAGE = os.getenv('RANGE42_INSTALLER_MAINTENANCE_TEST_IMAGE')
pytestmark = pytest.mark.skipif(not IMAGE, reason='requires explicit local durable-intent v2 image')


@pytest.mark.parametrize('operation,failure', [('fresh', 'stop'), ('update', 'stop'), ('update', 'rollback_ready')])
def test_actual_failed_cutover_survives_installer_exit_and_container_restart(tmp_path, monkeypatch, operation, failure):
    implementation = consumer()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    root = tmp_path / ('managed-' + uuid.uuid4().hex[:10])
    raw = {'root': str(root), 'name': root.name, 'image': IMAGE, 'uid': os.getuid(), 'gid': os.getgid(),
           'listen_address': '127.0.0.1', 'port': port}
    docker = implementation.DockerCLI()
    old = None
    verify = implementation.verify_ready
    def failure_on_candidate(transport, identifier):
        verify(transport, identifier)
        if identifier != old:
            raise ValueError('injected candidate rejection after actual readiness')
        if failure == 'rollback_ready':
            raise ValueError('injected rollback readiness failure')
    class StopFailure(implementation.DockerCLI):
        def stop(self, identifier):
            if failure == 'stop' and identifier != old:
                raise ValueError('injected candidate Docker stop failure')
            return super().stop(identifier)
    def status(path, token=None):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        try:
            with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}' + path, headers=headers), timeout=2) as response:
                return response.status
        except urllib.error.HTTPError as response:
            return response.code
    def health():
        for _ in range(100):
            try:
                if status('/v1/health') == 200:
                    return
            except OSError:
                pass
            time.sleep(.1)
        pytest.fail('disposable candidate did not become live')
    try:
        if operation == 'update':
            assert implementation.apply(raw)['status'] == 'ready'
            old = implementation.read_json(root / 'installation.json')['container_id']
            raw['cors_origins'] = ['http://127.0.0.1:3999']
        monkeypatch.setattr(implementation, 'DockerCLI', StopFailure)
        monkeypatch.setattr(implementation, 'verify_ready', failure_on_candidate)
        with pytest.raises(ValueError, match='injected'):
            implementation.apply(raw, operation=operation)
        pending = implementation.read_json(root / 'pending.json')
        candidate = pending['container_id']
        assert docker.inspect(candidate)['State']['Running'] is (failure == 'stop')
        if old:
            assert docker.inspect(old)['State']['Running'] is (failure == 'rollback_ready')
        active = old if failure == 'rollback_ready' else candidate
        token = (root / 'secrets/api-token').read_text().strip()
        lock = root / 'state/maintenance.lock'
        inode = lock.stat().st_ino
        assert lock.stat().st_size > 0
        ready_status = status('/v1/health/ready', token)
        assert ready_status == 503
        admin_status = status('/v1/admin/maintenance', token)
        assert admin_status == 503
        assert status('/v1/admin/maintenance') == 401
        assert status('/v1/health') == 200
        docker._run(['restart', '--time', '10', active], timeout=30)
        health()
        ready_status = status('/v1/health/ready', token)
        assert ready_status == 503
        assert lock.stat().st_ino == inode and lock.stat().st_size > 0
        with pytest.raises(ValueError, match='pending|incomplete|unknown legacy'):
            implementation.apply(raw)
    finally:
        ids = set()
        for record in [root / 'pending.json', root / 'installation.json']:
            if record.exists():
                data = json.loads(record.read_text())
                ids.update(data[key] for key in ('container_id', 'previous_container_id') if data.get(key))
        for identifier in ids:
            docker._run(['rm', '--force', identifier], timeout=30)
        networks = docker._run(['network', 'ls', '--quiet', '--filter', 'label=org.range42.installation=' + str(root)]).splitlines()
        for network in networks:
            docker._run(['network', 'rm', network])
