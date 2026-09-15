"""Paired real HTTP admission with an injected local Docker failure boundary."""
import importlib
import json
import os
from pathlib import Path

import pytest

from test_backend_container_consumer import consumer, config

API_SOURCE = os.environ.get('RANGE42_INSTALLER_API_SOURCE')
pytestmark = pytest.mark.skipif(not API_SOURCE, reason='set paired API source for actual HTTP admission checks')


@pytest.mark.parametrize('failure', ['stop', 'inspect'])
def test_failed_fresh_candidate_remains_fenced_after_installer_exit_and_api_restart(tmp_path, monkeypatch, failure):
    monkeypatch.syspath_prepend(API_SOURCE)
    monkeypatch.setenv('PROJECT_ROOT_DIR', API_SOURCE)
    monkeypatch.setenv('RANGE42_AUTH_MODE', 'development')
    monkeypatch.setenv('RANGE42_WORKSPACE_ROOT', str(tmp_path / 'workspaces'))
    from fastapi.testclient import TestClient
    from app import main
    from app.core.config import Settings

    implementation = consumer()
    plan = implementation.validate_config(config(tmp_path))
    clients = []
    running = False
    stop_attempted = False
    identifier = 'c' * 64

    def api():
        monkeypatch.setenv('RANGE42_AUTH_MODE', 'required')
        monkeypatch.setenv('RANGE42_API_TOKEN_FILE', str(Path(plan['secrets_dir']) / 'api-token'))
        monkeypatch.delenv('RANGE42_API_TOKEN', raising=False)
        monkeypatch.setenv('RANGE42_CREDENTIAL_KEY_FILE', str(Path(plan['secrets_dir']) / 'credential-key'))
        monkeypatch.delenv('RANGE42_CREDENTIAL_KEY', raising=False)
        monkeypatch.setenv('RANGE42_MAINTENANCE_LOCK_FILE', str(Path(plan['state_dir']) / 'maintenance.lock'))
        monkeypatch.setattr(main, 'settings', Settings())
        return TestClient(main.create_app())

    class Docker:
        def _run(self, args, **kwargs):
            nonlocal running
            if args[:2] == ['image', 'inspect']:
                return json.dumps([{'Id': plan['image']}])
            if args[0] == 'run':
                return importlib.import_module('app.core.maintenance').PROTOCOL
            if args[0] == 'start':
                running = True
                clients.append(api())
                return ''
            raise AssertionError('Unexpected Docker command')

        def stop(self, value):
            nonlocal stop_attempted
            assert value == identifier
            stop_attempted = True
            if failure == 'stop':
                raise ValueError('injected stop failure')
            # Lost Docker acknowledgement leaves actual candidate state unknown.

        def inspect(self, value):
            assert value == identifier
            if stop_attempted:
                raise ValueError('injected inspection failure')
            return {'State': {'Running': running}, 'Image': plan['image']}

    monkeypatch.setattr(implementation, 'DockerCLI', Docker)
    monkeypatch.setattr(implementation, 'create_candidate', lambda *args: identifier)
    monkeypatch.setattr(implementation, 'wait_health', lambda *args: None)
    monkeypatch.setattr(implementation, 'verify_ready', lambda *args: (_ for _ in ()).throw(ValueError('injected readiness failure')))
    with pytest.raises(ValueError):
        implementation.apply(config(tmp_path), operation='fresh')
    assert running and stop_attempted
    token = (Path(plan['secrets_dir']) / 'api-token').read_text().strip()
    headers = {'Authorization': 'Bearer ' + token}
    lock = Path(plan['state_dir']) / 'maintenance.lock'
    inode = lock.stat().st_ino
    for client in [clients[0], api()]:
        capability = client.get('/v1/admin/maintenance', headers=headers)
        assert capability.status_code == 503
        assert client.post('/v0/admin/run/bundles/test/run', headers=headers).status_code == 503
        assert client.get('/v1/admin/maintenance').status_code == 401
        assert client.get('/v1/health').status_code == 200
    assert lock.stat().st_ino == inode and lock.stat().st_size > 0
    assert (Path(plan['root']) / 'pending.json').exists()


def test_installer_probe_refuses_preexisting_intent_even_under_external_flock(tmp_path, monkeypatch):
    import importlib.util
    from test_backend_container_consumer import FILES
    import fcntl

    monkeypatch.syspath_prepend(API_SOURCE)
    from app.core.maintenance import MaintenanceGate
    path = tmp_path / 'maintenance.lock'
    gate = MaintenanceGate(path)
    gate.capability()
    spec = importlib.util.spec_from_file_location('intent_probe', FILES / 'container_maintenance_probe.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    with path.open('r+b') as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        holder.write(b'previous cutover\n')
        holder.flush()
        os.fsync(holder.fileno())
        with pytest.raises(ValueError, match='intent|recovery'):
            probe.require_external_fence(gate)
    assert path.read_bytes() == b'previous cutover\n'
