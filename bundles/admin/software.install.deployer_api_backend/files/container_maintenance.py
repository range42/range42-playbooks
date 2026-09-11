"""Keep installer admission held while replacing one verified local container."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import selectors
import stat
import subprocess
import time

PROTOCOL = 'flock-http-intent-v2'
MAX_MESSAGE = 4096


def validate_proof(proof: dict) -> None:
    if (not isinstance(proof, dict) or set(proof) != {'protocol', 'enabled', 'process', 'lock'}
            or proof['protocol'] != PROTOCOL or proof['enabled'] is not True):
        raise ValueError('Maintenance capability is missing or unsupported')
    process, lock = proof['process'], proof['lock']
    if (not isinstance(process, dict) or set(process) != {'pid', 'start_time', 'boot_id'}
            or type(process['pid']) is not int or process['pid'] <= 0
            or not isinstance(process['start_time'], str) or not process['start_time'].isascii()
            or not process['start_time'].isdigit() or len(process['start_time']) > 32
            or not isinstance(process['boot_id'], str) or not 1 <= len(process['boot_id']) <= 128):
        raise ValueError('Maintenance process identity is invalid')
    if (not isinstance(lock, dict) or set(lock) != {'path', 'device', 'inode', 'uid'}
            or not isinstance(lock['path'], str) or not Path(lock['path']).is_absolute()
            or len(lock['path']) > 1024 or '..' in Path(lock['path']).parts
            or any(type(lock[key]) is not int or lock[key] < 0 for key in ('device', 'inode', 'uid'))):
        raise ValueError('Maintenance lock identity is invalid')


def _acknowledgement(stream, deadline: float) -> dict:
    data = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(stream, selectors.EVENT_READ)
        while b'\n' not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise ValueError('Maintenance acknowledgement timed out')
            chunk = os.read(stream.fileno(), MAX_MESSAGE + 1 - len(data))
            if not chunk:
                raise ValueError('Maintenance helper closed before acknowledging idle state')
            data.extend(chunk)
            if len(data) > MAX_MESSAGE:
                raise ValueError('Maintenance acknowledgement exceeds its size limit')
    try:
        line, tail = bytes(data).split(b'\n', 1)
        if tail:
            raise ValueError('trailing data')
        return json.loads(line)
    except (ValueError, UnicodeError):
        raise ValueError('Maintenance acknowledgement is malformed') from None


def _close_helper(process: subprocess.Popen) -> None:
    try:
        process.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    finally:
        process.stdout.close()


@contextmanager
def held_maintenance(command: list[str], proof: dict, *, timeout: float = 10, environment: dict | None = None):
    """Send one bounded proof, retain stdin, and accept only its bound idle reply."""
    validate_proof(proof)
    encoded = (json.dumps(proof, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if len(encoded) > MAX_MESSAGE or not 0 < timeout <= 60:
        raise ValueError('Maintenance proof or timeout exceeds its bound')
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, close_fds=True, env=environment)
    try:
        try:
            process.stdin.write(encoded)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            raise ValueError('Maintenance helper closed before reading the proof') from None
        reply = _acknowledgement(process.stdout, time.monotonic() + timeout)
        expected = {'status': 'idle', 'protocol': PROTOCOL,
                    'process': proof['process'], 'lock': proof['lock']}
        if reply != expected or process.poll() is not None:
            raise ValueError('Maintenance helper refused or could not bind idle state')
        yield process
    finally:
        _close_helper(process)


class AdmissionLock:
    """An already-existing private inode; never create, replace or repair it."""
    def __init__(self, path: Path, *, uid: int, gid: int):
        if not path.is_absolute() or path != path.resolve():
            raise ValueError('Admission path cannot contain symbolic links')
        parent = path.parent.stat()
        if parent.st_uid != uid or parent.st_mode & 0o022:
            raise ValueError('Admission directory must be private and owned by the API user')
        self.path = path
        self.descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        self.acquired = False
        self.intent = None
        try:
            self.original = os.fstat(self.descriptor)
            if (not stat.S_ISREG(self.original.st_mode) or self.original.st_nlink != 1
                    or (self.original.st_uid, self.original.st_gid) != (uid, gid)
                    or self.original.st_mode & 0o077):
                raise ValueError('Admission lock must be a private regular file owned by the API user')
            self.verify()
        except BaseException:
            os.close(self.descriptor)
            raise

    def verify(self) -> None:
        if self.path != self.path.resolve():
            raise ValueError('Admission lock path changed')
        current = self.path.lstat()
        attributes = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink')
        if any(getattr(current, key) != getattr(self.original, key) for key in attributes):
            raise ValueError('Admission lock identity changed')

    def acquire(self) -> None:
        self.verify()
        try:
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Admission lock is busy or held by another process') from None
        self.verify()
        if os.fstat(self.descriptor).st_size:
            raise ValueError('Unfinished maintenance intent requires explicit recovery')
        self.acquired = True

    def begin_intent(self) -> None:
        self.verify()
        if not self.acquired or self.intent is not None or os.fstat(self.descriptor).st_size:
            raise ValueError('Maintenance intent requires an empty exclusively owned inode')
        self.intent = (PROTOCOL + ':' + os.urandom(16).hex() + '\n').encode()
        if os.pwrite(self.descriptor, self.intent, 0) != len(self.intent):
            raise ValueError('Maintenance intent could not be written completely')
        os.fsync(self.descriptor)

    def complete(self) -> None:
        self.verify()
        if (not self.acquired or self.intent is None
                or os.pread(self.descriptor, len(self.intent) + 1, 0) != self.intent):
            raise ValueError('Only the owned maintenance intent can be completed')
        try:
            os.ftruncate(self.descriptor, 0)
            os.fsync(self.descriptor)
        except BaseException:
            # A failed clear must not intentionally reopen admission on exit.
            os.pwrite(self.descriptor, self.intent, 0)
            os.fsync(self.descriptor)
            raise
        self.intent = None

    def close(self) -> None:
        self.acquired = False
        os.close(self.descriptor)


@contextmanager
def host_admission(path: Path, *, uid: int, gid: int):
    gate = AdmissionLock(path, uid=uid, gid=gid)
    try:
        gate.acquire()
        yield gate
    finally:
        gate.close()


def _container_id(value: str) -> None:
    import re
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Maintenance requires the full immutable container ID')


def _container_snapshot(info: dict, identifier: str, proof: dict, state_dir: Path,
                        installation_root: Path, *, running: bool) -> dict:
    """Bind API proof to the owned container and the host inode it actually mounts."""
    try:
        state = info['State']
        if (info['Id'] != identifier or state['Running'] is not running
                or any(state.get(key) for key in ('Paused', 'Restarting', 'Dead'))
                or info['Config']['Labels']['org.range42.installation'] != str(installation_root)):
            raise ValueError('identity')
        environment = dict(item.split('=', 1) for item in info['Config']['Env'])
        if environment.get('RANGE42_MAINTENANCE_LOCK_FILE') != proof['lock']['path']:
            raise ValueError('lock configuration')
        lock_path = Path(proof['lock']['path'])
        matches = [mount for mount in info['Mounts']
                   if lock_path.is_relative_to(mount['Destination'])]
        if len(matches) != 1:
            raise ValueError('ambiguous mount')
        mount = matches[0]
        if (mount['Type'] != 'bind' or mount['RW'] is not True
                or mount['Destination'] != '/var/lib/range42'
                or Path(mount['Source']) != state_dir
                or lock_path.relative_to(mount['Destination']) != Path('maintenance.lock')):
            raise ValueError('binding')
        return {'Id': info['Id'], 'Image': info['Image'],
                'Mounts': sorted(info['Mounts'], key=lambda item: json.dumps(item, sort_keys=True)),
                'Config': info['Config'], 'RestartCount': info['RestartCount']}
    except (KeyError, TypeError, ValueError):
        raise ValueError('Maintenance container identity or persistent binding cannot be verified') from None


def _bound_gate(gate: AdmissionLock, proof: dict) -> None:
    gate.verify()
    expected = proof['lock']
    if (gate.original.st_dev, gate.original.st_ino, gate.original.st_uid) != (
            expected['device'], expected['inode'], expected['uid']):
        raise ValueError('Maintenance proof does not identify the host admission inode')


@contextmanager
def stopped_container(docker, identifier: str, proof: dict, *, state_dir: Path,
                      installation_root: Path, uid: int, gid: int, timeout: float = 10):
    """Continuously fence admission, audit idle, and stop only the verified ID.

    The caller must serialize installation changes and inspect the exact ID on
    failure: a failed stop or inspection can leave it stopped. No source/state rollback or
    container restart is performed by this mechanism. The caller completes its
    owned intent only after verified readiness and managed state commit; leaving
    this scope closes flock but preserves any unfinished intent.
    """
    _container_id(identifier)
    validate_proof(proof)
    if (state_dir != state_dir.resolve() or installation_root != installation_root.resolve()
            or not state_dir.is_absolute() or not installation_root.is_absolute()):
        raise ValueError('Maintenance paths must be local absolute paths without symbolic links')
    initial = docker.inspect(identifier)
    baseline = _container_snapshot(initial, identifier, proof, state_dir, installation_root, running=True)
    gate = AdmissionLock(state_dir / 'maintenance.lock', uid=uid, gid=gid)
    try:
        _bound_gate(gate, proof)
        # Own admission independently of the exec pipe or old container lifetime.
        gate.acquire()
        with held_maintenance(docker.guard_command(identifier), proof, timeout=timeout,
                              environment=getattr(docker, "environment", None)) as helper:
            current = docker.inspect(identifier)
            before_stop = _container_snapshot(current, identifier, proof, state_dir, installation_root, running=True)
            changed = sorted(key for key in baseline if before_stop[key] != baseline[key])
            if (changed or current['State']['Pid'] != initial['State']['Pid']
                    or current['State']['StartedAt'] != initial['State']['StartedAt']):
                raise ValueError('Maintenance container identity changed before stop: ' + ', '.join(changed))
            _bound_gate(gate, proof)
            if helper.poll() is not None:
                raise ValueError('Maintenance helper exited before controlled stop')
            gate.begin_intent()
            docker.stop(identifier)
            stopped = docker.inspect(identifier)
            after_stop = _container_snapshot(stopped, identifier, proof, state_dir, installation_root, running=False)
            changed = sorted(key for key in baseline if after_stop[key] != baseline[key])
            if changed:
                raise ValueError('Maintenance container identity changed during stop: ' + ', '.join(changed))
            try:
                helper.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                raise ValueError('Maintenance helper survived the reported container stop') from None
            _bound_gate(gate, proof)
            # The host has held this original inode continuously since the audit.
            try:
                yield gate
            finally:
                gate.verify()
    finally:
        gate.close()


class DockerCLI:
    """Only a local Unix daemon can share the installer's filesystem flock."""
    def __init__(self, *, executable: str = 'docker', socket: Path = Path('/var/run/docker.sock')):
        if not socket.is_absolute() or '..' in socket.parts:
            raise ValueError('Maintenance requires a local absolute Docker Unix socket')
        self.prefix = [executable, '--host', 'unix://' + str(socket)]
        self.environment = {key: value for key, value in os.environ.items()
                            if key not in ('DOCKER_HOST', 'DOCKER_CONTEXT')}

    def _run(self, arguments: list[str], *, timeout: int = 15) -> str:
        try:
            result = subprocess.run(self.prefix + arguments, env=self.environment,
                                    stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError('Local Docker maintenance command could not complete') from None
        if result.returncode or len(result.stdout) > 1024 * 1024:
            raise ValueError('Local Docker maintenance command failed or exceeded its output bound')
        return result.stdout

    def inspect(self, identifier: str) -> dict:
        _container_id(identifier)
        try:
            rows = json.loads(self._run(['inspect', '--type', 'container', identifier]))
            if not isinstance(rows, list) or len(rows) != 1 or rows[0]['Id'] != identifier:
                raise ValueError('identity')
            return rows[0]
        except (KeyError, TypeError, ValueError):
            raise ValueError('Local Docker container identity cannot be verified') from None

    def guard_command(self, identifier: str) -> list[str]:
        _container_id(identifier)
        probe = Path(__file__).with_name('container_maintenance_probe.py').read_text()
        return self.prefix + ['exec', '--interactive', identifier, 'python', '-c', probe]

    def stop(self, identifier: str) -> None:
        _container_id(identifier)
        self._run(['stop', '--time', '60', identifier], timeout=75)
