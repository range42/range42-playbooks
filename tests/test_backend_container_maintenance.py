"""Exercise held installer subprocess and filesystem admission, without Docker."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

FILE = Path(__file__).resolve().parents[1] / 'bundles/admin/software.install.deployer_api_backend/files/container_maintenance.py'
PROOF = {'protocol': 'flock-http-v1', 'enabled': True,
         'process': {'pid': 1, 'start_time': '10', 'boot_id': 'test'},
         'lock': {'path': '/state/maintenance.lock', 'device': 1, 'inode': 2, 'uid': 1000}}


def module():
    assert FILE.exists(), 'installer must retain maintenance admission through controlled stop'
    spec = importlib.util.spec_from_file_location('container_maintenance', FILE)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_helper_stdin_stays_open_until_controlled_stop_scope_ends(tmp_path):
    released = tmp_path / 'released'
    code = 'import sys,json; proof=json.loads(sys.stdin.readline()); print(json.dumps({"status":"idle","protocol":proof["protocol"],"process":proof["process"],"lock":proof["lock"]}),flush=True); sys.stdin.read(1); open(sys.argv[1],"w").write("released")'
    with module().held_maintenance([sys.executable, '-c', code, str(released)], PROOF, timeout=2) as process:
        assert process.poll() is None
        assert not released.exists()
        process.stdin.flush()
    assert released.read_text() == 'released'


@pytest.mark.parametrize('response', [{'status': 'refused'}, {'status': 'idle', 'process': {'pid': 99}}, []])
def test_refused_or_unbound_acknowledgement_never_enters_update_scope(response):
    code = 'import sys,json; sys.stdin.readline(); print(sys.argv[1],flush=True);sys.stdin.read(1)'
    entered = False
    with pytest.raises(ValueError, match='maintenance|Maintenance'):
        with module().held_maintenance([sys.executable, '-c', code, json.dumps(response)], PROOF, timeout=2):
            entered = True
    assert not entered


def test_host_admission_holds_same_inode_and_blocks_another_process(tmp_path):
    path = tmp_path / 'maintenance.lock'
    path.touch(mode=0o600)
    before = path.stat().st_ino
    with module().host_admission(path, uid=os.getuid(), gid=os.getgid()):
        result = subprocess.run([sys.executable, '-c', 'import sys,fcntl;f=open(sys.argv[1],"r");fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)', str(path)], capture_output=True)
        assert result.returncode != 0
        assert path.stat().st_ino == before
    result = subprocess.run([sys.executable, '-c', 'import sys,fcntl;f=open(sys.argv[1],"r");fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)', str(path)], capture_output=True)
    assert result.returncode == 0


def test_host_admission_refuses_another_holder_or_a_symlink(tmp_path):
    path = tmp_path / 'gate'
    path.touch(mode=0o600)
    with module().host_admission(path, uid=os.getuid(), gid=os.getgid()):
        with pytest.raises(ValueError, match='held|busy'):
            with module().host_admission(path, uid=os.getuid(), gid=os.getgid()):
                pytest.fail('second installer entered')
    alias = tmp_path / 'alias'
    alias.symlink_to(path)
    with pytest.raises(ValueError, match='symlink|symbolic'):
        with module().host_admission(alias, uid=os.getuid(), gid=os.getgid()):
            pytest.fail('linked gate accepted')


def proof_for(path):
    info = path.stat()
    return {**PROOF, 'lock': {'path': '/var/lib/range42/maintenance.lock',
            'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid}}


class LocalContainer:
    """Fake Docker identity/stop boundary, backed by a real held probe child."""
    def __init__(self, tmp_path):
        import copy
        self.root = tmp_path
        self.gate = tmp_path / 'maintenance.lock'
        self.gate.touch(mode=0o600)
        self.container_id = 'a' * 64
        self.calls = []
        self.info = {'Id': self.container_id, 'Image': 'sha256:' + 'b' * 64,
                     'RestartCount': 0,
                     'State': {'Running': True, 'Paused': False, 'Restarting': False,
                               'Dead': False, 'Pid': 123, 'StartedAt': 'initial'},
                     'Config': {'Labels': {'org.range42.installation': str(tmp_path)},
                                'Env': ['RANGE42_MAINTENANCE_LOCK_FILE=/var/lib/range42/maintenance.lock']},
                     'Mounts': [{'Type': 'bind', 'Source': str(tmp_path),
                                 'Destination': '/var/lib/range42', 'RW': True}]}
        self.copy = copy.deepcopy
        self.inspections = 0
        self.before_second_inspect = None
        self.stop_failure = False

    def inspect(self, container_id):
        self.calls.append(('inspect', container_id))
        self.inspections += 1
        if self.inspections == 2 and self.before_second_inspect:
            self.before_second_inspect()
        return self.copy(self.info)

    def guard_command(self, container_id):
        self.calls.append(('guard', container_id))
        code = ('import sys,json,os,fcntl; p=json.loads(sys.stdin.readline()); '
                'open(sys.argv[2],"w").write(str(os.getpid())); '
                'print(json.dumps({"status":"idle","protocol":p["protocol"],"process":p["process"],"lock":p["lock"]}),flush=True); '
                'sys.stdin.read(1)')
        return [sys.executable, '-c', code, str(self.gate), str(self.root / 'helper.pid')]

    def stop(self, container_id):
        import signal
        self.calls.append(('stop', container_id))
        assert container_id == self.container_id
        if self.stop_failure:
            raise ValueError('stop refused')
        os.kill(int((self.root / 'helper.pid').read_text()), signal.SIGTERM)
        self.info['State']['Running'] = False
        self.info['State']['Pid'] = 0


def stop_scope(docker, **kwargs):
    implementation = module()
    assert hasattr(implementation, 'stopped_container'), 'need exact-ID stop and host-lock handover'
    return implementation.stopped_container(docker, docker.container_id,
            proof_for(docker.gate), state_dir=docker.root, installation_root=docker.root,
            uid=os.getuid(), gid=os.getgid(), **kwargs)


def shared_lock_available(path):
    return subprocess.run([sys.executable, '-c',
        'import sys,fcntl;f=open(sys.argv[1],"r");fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)',
        str(path)], capture_output=True).returncode == 0


def test_exact_container_stop_hands_existing_inode_to_host_until_update_exits(tmp_path):
    docker = LocalContainer(tmp_path)
    inode = docker.gate.stat().st_ino
    with stop_scope(docker) as lease:
        assert not docker.info['State']['Running']
        assert not shared_lock_available(docker.gate)
        assert docker.gate.stat().st_ino == inode
        lease.verify()
    assert shared_lock_available(docker.gate)
    assert ('stop', docker.container_id) in docker.calls
    assert all(identifier == docker.container_id for _, identifier in docker.calls)


@pytest.mark.parametrize('mutation', ['id', 'owner', 'mount', 'image', 'process', 'restart', 'gate'])
def test_changed_container_or_admission_identity_refuses_stop(tmp_path, mutation):
    docker = LocalContainer(tmp_path)
    def change():
        if mutation == 'id':
            docker.info['Id'] = 'c' * 64
        elif mutation == 'owner':
            docker.info['Config']['Labels']['org.range42.installation'] = '/foreign'
        elif mutation == 'mount':
            docker.info['Mounts'][0]['Source'] = '/foreign'
        elif mutation == 'image':
            docker.info['Image'] = 'sha256:' + 'd' * 64
        elif mutation == 'process':
            docker.info['State']['Pid'] += 1
        elif mutation == 'restart':
            docker.info['RestartCount'] += 1
        else:
            docker.gate.rename(tmp_path / 'previous-gate')
            docker.gate.touch(mode=0o600)
    docker.before_second_inspect = change
    with pytest.raises(ValueError):
        with stop_scope(docker):
            pytest.fail('unverified state entered update')
    assert not any(operation == 'stop' for operation, _ in docker.calls)
    assert docker.info['State']['Running']


def test_unverified_bind_mount_refuses_before_launching_helper(tmp_path):
    docker = LocalContainer(tmp_path)
    docker.info['Mounts'][0]['RW'] = False
    with pytest.raises(ValueError):
        with stop_scope(docker):
            pytest.fail('read-only state accepted')
    assert [operation for operation, _ in docker.calls] == ['inspect']


def test_stop_failure_releases_helper_without_entering_update_or_touching_state(tmp_path):
    docker = LocalContainer(tmp_path)
    docker.stop_failure = True
    sentinel = tmp_path / 'state.db'
    sentinel.write_bytes(b'original-state')
    with pytest.raises(ValueError):
        with stop_scope(docker):
            pytest.fail('failed stop entered update')
    assert docker.info['State']['Running']
    assert shared_lock_available(docker.gate)
    assert sentinel.read_bytes() == b'original-state'


def test_replacement_gate_during_update_is_reported_without_unlinking_either_inode(tmp_path):
    docker = LocalContainer(tmp_path)
    with pytest.raises(ValueError, match='identity|changed'):
        with stop_scope(docker):
            docker.gate.rename(tmp_path / 'original-gate')
            docker.gate.touch(mode=0o600)
    assert (tmp_path / 'original-gate').is_file() and docker.gate.is_file()


@pytest.mark.parametrize('identifier', ['api-name', 'a' * 12, '../api', 'A' * 64])
def test_only_full_immutable_container_ids_can_be_stopped(tmp_path, identifier):
    docker = LocalContainer(tmp_path)
    docker.container_id = identifier
    with pytest.raises(ValueError):
        with stop_scope(docker):
            pytest.fail('mutable identifier accepted')
    assert docker.calls == []


def test_helper_partial_acknowledgement_is_bounded_and_closed(tmp_path):
    released = tmp_path / 'released'
    code = ('import sys;sys.stdin.readline();sys.stdout.write("{");sys.stdout.flush();'
            'sys.stdin.read(1);open(sys.argv[1],"w").write("released")')
    with pytest.raises(ValueError, match='timed out'):
        with module().held_maintenance([sys.executable, '-c', code, str(released)], PROOF, timeout=0.05):
            pytest.fail('partial reply authorized maintenance')
    assert released.read_text() == 'released'


def test_raw_helper_output_is_never_in_the_error_or_console(capsys):
    private = 'private-output-must-not-be-echoed'
    code = 'import sys;sys.stdin.readline();print(sys.argv[1],flush=True);print(sys.argv[1],file=sys.stderr);sys.stdin.read(1)'
    with pytest.raises(ValueError) as error:
        with module().held_maintenance([sys.executable, '-c', code, private], PROOF):
            pytest.fail('bad output authorized maintenance')
    assert private not in str(error.value)
    captured = capsys.readouterr()
    assert private not in captured.out + captured.err


def test_helper_death_before_stop_refuses_update_and_leaves_container_running(tmp_path):
    import signal
    import time
    docker = LocalContainer(tmp_path)
    def kill_helper():
        os.kill(int((tmp_path / 'helper.pid').read_text()), signal.SIGTERM)
        time.sleep(0.03)
    docker.before_second_inspect = kill_helper
    with pytest.raises(ValueError, match='helper exited'):
        with stop_scope(docker):
            pytest.fail('dead helper authorized stop')
    assert docker.info['State']['Running']
    assert not any(operation == 'stop' for operation, _ in docker.calls)


def test_local_docker_transport_uses_only_the_pinned_id_and_unix_endpoint(tmp_path, monkeypatch):
    implementation = module()
    assert hasattr(implementation, 'DockerCLI'), 'transport must bind inspect, exec and stop to exact local Docker ID'
    executable = tmp_path / 'docker-fixture'
    calls = tmp_path / 'calls'
    executable.write_text('#!' + sys.executable + '\nimport json,sys,os\n'
        'with open(os.environ["TEST_CALLS"],"a") as stream:stream.write(json.dumps({"args":sys.argv[1:],"context":os.getenv("DOCKER_CONTEXT"),"host":os.getenv("DOCKER_HOST")})+"\\n")\n'
        'print(json.dumps([{"Id":sys.argv[-1]}]))\n')
    executable.chmod(0o700)
    monkeypatch.setenv('TEST_CALLS', str(calls))
    monkeypatch.setenv('DOCKER_HOST', 'tcp://remote.invalid:2375')
    monkeypatch.setenv('DOCKER_CONTEXT', 'unrelated-context')
    docker = implementation.DockerCLI(executable=str(executable), socket=tmp_path / 'docker.sock')
    identifier = 'a' * 64
    assert docker.inspect(identifier)['Id'] == identifier
    docker.stop(identifier)
    command = docker.guard_command(identifier)
    assert command[-6:-1] == ['exec', '--interactive', identifier, 'python', '-c']
    assert command[-1] == FILE.with_name('container_maintenance_probe.py').read_text()
    records = [json.loads(line) for line in calls.read_text().splitlines()]
    assert all(record['args'][:2] == ['--host', 'unix://' + str(tmp_path / 'docker.sock')] for record in records)
    assert all(record['context'] is None and record['host'] is None for record in records)
    assert records[1]['args'][-4:] == ['stop', '--time', '60', identifier]


def test_docker_inspect_cannot_substitute_a_different_container(tmp_path):
    implementation = module()
    assert hasattr(implementation, 'DockerCLI')
    executable = tmp_path / 'docker-fixture'
    executable.write_text('#!' + sys.executable + '\nprint(\'[{"Id":"' + 'b' * 64 + '"}]\')\n')
    executable.chmod(0o700)
    with pytest.raises(ValueError, match='identity'):
        implementation.DockerCLI(executable=str(executable)).inspect('a' * 64)


def test_admission_survives_helper_loss_while_old_api_is_still_running(tmp_path):
    import signal
    import time
    docker = LocalContainer(tmp_path)
    def stop_after_helper_loss(identifier):
        docker.calls.append(('stop', identifier))
        os.kill(int((tmp_path / 'helper.pid').read_text()), signal.SIGTERM)
        time.sleep(0.03)
        assert docker.info['State']['Running']
        assert not shared_lock_available(docker.gate), 'helper loss reopened HTTP before old API stopped'
        docker.info['State']['Running'] = False
        docker.info['State']['Pid'] = 0
    docker.stop = stop_after_helper_loss
    with stop_scope(docker):
        assert not shared_lock_available(docker.gate)
    assert shared_lock_available(docker.gate)


def test_inspect_mount_order_does_not_change_mount_identity(tmp_path):
    docker = LocalContainer(tmp_path)
    docker.info['Mounts'].append({'Type': 'bind', 'Source': '/readonly-runtime',
                                 'Destination': '/runtime', 'RW': False})
    docker.before_second_inspect = lambda: docker.info['Mounts'].reverse()
    with stop_scope(docker):
        assert not docker.info['State']['Running']
