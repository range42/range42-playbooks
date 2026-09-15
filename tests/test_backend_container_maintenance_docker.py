"""Opt-in, disposable Docker proof of container-to-host admission handover."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'bundles/admin/software.install.deployer_api_backend/files'
IMAGE = os.getenv('RANGE42_INSTALLER_MAINTENANCE_TEST_IMAGE')
pytestmark = pytest.mark.skipif(not IMAGE, reason='set immutable local maintenance image for disposable Docker acceptance')


def load(name):
    spec = importlib.util.spec_from_file_location(name, FILES / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize('lose_probe_during_stop', [False, True])
def test_old_container_stop_retains_host_admission_through_replacement(tmp_path, lose_probe_during_stop):
    assert IMAGE.startswith('sha256:') and len(IMAGE) == 71
    root = tmp_path / ('installer-' + uuid.uuid4().hex[:12])
    root.mkdir(mode=0o700)
    state = root / 'state'
    state.mkdir(mode=0o700)
    credentials = root / 'secrets'
    load('container_install').provision_credentials(credentials, state / 'workspaces/.range42.db',
                                                   uid=os.getuid(), gid=os.getgid())
    token = (credentials / 'api-token').read_text().strip()
    maintenance = load('container_maintenance')
    docker = maintenance.DockerCLI()
    containers = []

    def cli(*arguments):
        result = subprocess.run(docker.prefix + list(arguments), env=docker.environment,
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError('Disposable Docker fixture command failed')
        return result.stdout.strip()

    def start(suffix):
        identifier = cli('run', '--detach', '--init', '--name', root.name + '-' + suffix,
            '--label', 'org.range42.installation=' + str(root), '--read-only',
            '--user', f'{os.getuid()}:{os.getgid()}', '--tmpfs', '/tmp:mode=1777,size=256m',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--mount', f'type=bind,src={state},dst=/var/lib/range42',
            '--mount', f'type=bind,src={credentials / "api-token"},dst=/run/secrets/api_token,readonly',
            '--mount', f'type=bind,src={credentials / "credential-key"},dst=/run/secrets/credential_key,readonly',
            '--env', 'RANGE42_API_TOKEN_FILE=/run/secrets/api_token',
            '--env', 'RANGE42_CREDENTIAL_KEY_FILE=/run/secrets/credential_key',
            '--publish', '127.0.0.1::8000', IMAGE)
        containers.append(identifier)
        port = docker.inspect(identifier)['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort']
        return identifier, 'http://127.0.0.1:' + port

    def request(url, path, *, method='GET', authenticated=True):
        headers = {'Authorization': 'Bearer ' + token} if authenticated else {}
        data = b'{}' if method == 'POST' else None
        if data:
            headers['Content-Type'] = 'application/json'
        try:
            with urllib.request.urlopen(urllib.request.Request(url + path, data=data, headers=headers, method=method), timeout=2) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def wait_health(url):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if request(url, '/v1/health', authenticated=False)[0] == 200:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.1)
        pytest.fail('Disposable API did not become live')

    try:
        old, old_url = start('old')
        wait_health(old_url)
        assert request(old_url, '/v1/health/ready')[1]['ready']
        status, proof = request(old_url, '/v1/admin/maintenance')
        assert status == 200 and proof['enabled']
        original_inode = (state / 'maintenance.lock').stat().st_ino
        # The probe alone cannot authorize stop without its host admission fence.
        with pytest.raises(ValueError, match='refused'):
            with maintenance.held_maintenance(docker.guard_command(old), proof,
                                               environment=docker.environment):
                pytest.fail('Unfenced probe accepted maintenance')
        assert docker.inspect(old)['State']['Running'] is True
        if not lose_probe_during_stop:
            lock_root = state / 'workspaces/.locks'
            lock_root.mkdir(mode=0o700, exist_ok=True)
            provisioning = lock_root / 'provisioning.lock'
            provisioning.touch(mode=0o600, exist_ok=True)
            with provisioning.open('r') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with pytest.raises(ValueError, match='refused'):
                    with maintenance.stopped_container(docker, old, proof, state_dir=state,
                            installation_root=root, uid=os.getuid(), gid=os.getgid()):
                        pytest.fail('Busy provisioning entered update')
            assert docker.inspect(old)['State']['Running'] is True
            assert request(old_url, '/v1/health/ready')[1]['ready']
            # Exercise the installed strict artifact audit, without fabricating DB rows.
            workspace = state / 'workspaces/installer-audit-fixture'
            artifact = workspace / 'runner/unrecorded'
            artifact.mkdir(mode=0o700, parents=True)
            identity = artifact / 'process.json'
            identity.write_text('{"pid":0}')
            try:
                with pytest.raises(ValueError, match='refused'):
                    with maintenance.stopped_container(docker, old, proof, state_dir=state,
                            installation_root=root, uid=os.getuid(), gid=os.getgid()):
                        pytest.fail('Unverifiable runner entered update')
                assert identity.read_text() == '{"pid":0}'
                assert docker.inspect(old)['State']['Running'] is True
            finally:
                identity.unlink()
                artifact.rmdir()
                artifact.parent.rmdir()
                workspace.rmdir()
        if lose_probe_during_stop:
            original_stop = docker.stop
            probe = FILES.joinpath('container_maintenance_probe.py').read_text()
            def stop_after_probe_loss(identifier):
                # Kill only the one exact installer probe in this owned container.
                script = ('import os,signal,sys; from pathlib import Path; '
                          'pids=[int(p.name) for p in Path("/proc").iterdir() '
                          'if p.name.isdigit() and (p/"cmdline").read_bytes().split(b"\\0")[1:] '
                          '==[b"-c",sys.argv[1].encode(),b""]]; '
                          'assert len(pids)==1; os.kill(pids[0],signal.SIGKILL)')
                cli('exec', identifier, 'python', '-c', script, probe)
                assert docker.inspect(identifier)['State']['Running'] is True
                assert request(old_url, '/v1/health/ready')[0] == 503
                assert request(old_url, '/v1/sources', method='POST')[0] == 503
                original_stop(identifier)
            docker.stop = stop_after_probe_loss
        with maintenance.stopped_container(docker, old, proof, state_dir=state,
                installation_root=root, uid=os.getuid(), gid=os.getgid()) as gate:
            assert docker.inspect(old)['State']['Running'] is False
            replacement, replacement_url = start('replacement')
            wait_health(replacement_url)
            assert request(replacement_url, '/v1/health/ready')[0] == 503
            assert request(replacement_url, '/v1/sources', method='POST')[0] == 503
            assert request(replacement_url, '/v0/proxmox/vms/1/start', method='POST')[0] == 503
            assert request(replacement_url, '/v1/health/ready', authenticated=False)[0] == 401
            assert (state / 'maintenance.lock').stat().st_ino == original_inode
            gate.verify()
            from test_backend_container_consumer import consumer
            consumer().verify_ready(docker, replacement)
            gate.complete()
        assert request(replacement_url, '/v1/health/ready')[1]['ready']
        status, fresh = request(replacement_url, '/v1/admin/maintenance')
        assert status == 200 and fresh['lock'] == proof['lock']
        assert fresh['process'] != proof['process']
        assert docker.inspect(replacement)['State']['Running'] is True
    finally:
        for identifier in reversed(containers):
            cli('rm', '--force', identifier)
