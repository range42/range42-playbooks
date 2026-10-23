#!/usr/bin/env python3
"""Retire declared native guests before removing their exact SSH trust records."""
import fcntl
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from ipaddress import IPv4Address
from pathlib import Path


class LifecycleError(ValueError):
    """A fixed, credential-free native lifecycle diagnostic."""


def command(argv, *, data=None, timeout=180):
    result = subprocess.run(argv, input=data, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise LifecycleError('Native lifecycle command failed; no guest pin was retired')
    return result.stdout


def manifest_guests(path):
    if path.stat().st_size > 65536:
        raise LifecycleError('The scenario manifest exceeds its bound')
    document = json.loads(path.read_text())
    guests = document['vms']
    if document.get('scenario') != 'catalog_try' or not isinstance(guests, list) or not 1 <= len(guests) <= 20:
        raise LifecycleError('The scenario must declare bounded native guest targets')
    ids, names, ips = set(), set(), set()
    template_ids = {item['vm_id'] for item in document.get('templates', [])}
    for guest in guests:
        vmid, name, ip = guest['vm_id'], guest['vm_name'], guest['ip']
        if (type(vmid) is not int or vmid <= 0 or vmid in ids or vmid in template_ids
                or not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,126}', name) is None
                or name in names or str(IPv4Address(ip)) != ip or ip in ips):
            raise LifecycleError('Scenario guest allocation is invalid or overlaps a template')
        ids.add(vmid)
        names.add(name)
        ips.add(ip)
    return guests


def inventory():
    raw = command(['proxmox_vm.list.to.jsons.sh'])
    if len(raw.encode()) > 4 * 1024 * 1024:
        raise LifecycleError('Native VM inventory exceeds its bound')
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    ids = set()
    if len(rows) > 4096:
        raise LifecycleError('Native VM inventory exceeds its bound')
    for row in rows:
        if (not isinstance(row, dict) or type(row.get('vm_id')) is not int
                or row['vm_id'] <= 0 or row['vm_id'] in ids):
            raise LifecycleError('Native VM inventory is invalid or ambiguous')
        ids.add(row['vm_id'])
    return rows


def ssh_targets(guests, path):
    targets = []
    for guest in guests:
        argv = ['ssh', '-G', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'UserKnownHostsFile=' + json.dumps(str(path))]
        argv += shlex.split(os.environ.get('ANSIBLE_SSH_COMMON_ARGS', ''))
        argv += shlex.split(os.environ.get('ANSIBLE_SSH_EXTRA_ARGS', ''))
        argv += ['r42.' + guest['vm_name']]
        raw = command(argv, timeout=5)
        options = dict(line.split(' ', 1) for line in raw.splitlines() if ' ' in line)
        if options.get('hostname') != guest['ip'] or options.get('stricthostkeychecking') not in ('true', 'yes'):
            raise LifecycleError('Effective SSH destination differs from the declared native guest')
        port = int(options['port'])
        if not 1 <= port <= 65535:
            raise LifecycleError('Effective native SSH port is invalid')
        target = options.get('hostkeyalias')
        if target is None:
            target = guest['ip'] if port == 22 else '[' + guest['ip'] + ']:' + str(port)
        if len(target) > 253 or re.fullmatch(r'(?:[A-Za-z0-9][A-Za-z0-9_.:-]*|\[[0-9.]+\]:[0-9]+)', target) is None:
            raise LifecycleError('Effective native SSH host-key target is invalid')
        globals_ = options.get('globalknownhostsfile', '').split()
        if globals_ not in (['/dev/null'], ['none'], ['/etc/ssh/ssh_known_hosts', '/etc/ssh/ssh_known_hosts2']):
            raise LifecycleError('Automatic retirement cannot change custom global SSH trust')
        for filename in globals_:
            if (filename not in ('/dev/null', 'none') and Path(filename).is_file()
                    and matching_lines(Path(filename).read_bytes(), [target])):
                raise LifecycleError('Global guest trust requires attended retirement')
        targets.append(target)
    if len(set(targets)) != len(targets):
        raise LifecycleError('Multiple declared guests resolve to the same SSH trust target')
    return targets


def matching_lines(data, targets):
    matches = set()
    with tempfile.NamedTemporaryFile() as copied:
        copied.write(data)
        copied.flush()
        for target in targets:
            result = subprocess.run(['ssh-keygen', '-F', target, '-f', copied.name],
                                    capture_output=True, text=True, timeout=5, check=False)
            if result.returncode not in (0, 1) or result.stderr:
                raise LifecycleError('Cannot inspect the selected guest trust records')
            for line in result.stdout.splitlines():
                if not line or line.startswith('#'):
                    continue
                fields = line.split()
                if (len(fields) < 3 or fields[0].startswith('@')
                        or (fields[0] != target and not fields[0].startswith('|1|'))
                        or ',' in fields[0]):
                    raise LifecycleError('Ambiguous, marked or shared guest trust requires attended retirement')
                matches.add(line)
    return matches


def snapshot(info):
    if info is None:
        return None
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink)


def read_pins(parent, name, managed):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except FileNotFoundError:
        return b'', None
    try:
        info = os.fstat(fd)
        allowed = (0o600,) if managed else (0o600, 0o644)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024 * 1024
                or info.st_uid != os.geteuid() or info.st_gid != os.getegid()
                or stat.S_IMODE(info.st_mode) not in allowed):
            raise LifecycleError('Guest trust must be a bounded, owned and non-writable regular file')
        data = os.read(fd, 1024 * 1024 + 1)
        after = os.fstat(fd)
        if len(data) > 1024 * 1024 or snapshot(info) != snapshot(after):
            raise LifecycleError('Guest trust changed during inspection')
        return data, info
    finally:
        os.close(fd)


@contextmanager
def locked_pins(path, targets, managed):
    if not path.is_absolute() or path.resolve() != path:
        raise LifecycleError('Guest trust path must be absolute and contain no symlinks')
    if not path.parent.exists():
        yield lambda: None
        if path.exists() or path.is_symlink():
            raise LifecycleError('Guest trust appeared during native retirement')
        return
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock = None
    try:
        info = os.fstat(parent)
        if info.st_uid != os.geteuid() or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise LifecycleError('Guest trust directory must remain private and owned by the controller')
        lock = os.open('.' + path.name + '.range42-lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        info = os.fstat(lock)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) != 0o600):
            raise LifecycleError('Guest trust lock must remain a private owned regular file')
        deadline = time.monotonic() + 5
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LifecycleError('Guest trust is busy; no deletion was attempted') from None
                time.sleep(0.05)
        original, before = read_pins(parent, path.name, managed)
        matches = matching_lines(original, targets)

        def retire():
            current, after = read_pins(parent, path.name, managed)
            if snapshot(before) != snapshot(after) or current != original:
                raise LifecycleError('Guest trust changed during native deletion; no pin was retired')
            if not matches:
                return
            remaining = b''.join(line for line in original.splitlines(keepends=True)
                                 if line.decode().rstrip('\r\n') not in matches)
            if remaining == original or matching_lines(remaining, targets):
                raise LifecycleError('Exact guest trust retirement could not be verified')
            original_parent = os.fstat(parent)
            visible_parent = path.parent.stat()
            if (original_parent.st_dev, original_parent.st_ino) != (visible_parent.st_dev, visible_parent.st_ino):
                raise LifecycleError('Guest trust directory changed during native deletion')
            temporary = '.retired-guest-' + secrets.token_hex(16)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         stat.S_IMODE(before.st_mode), dir_fd=parent)
            try:
                with os.fdopen(fd, 'wb') as staged:
                    staged.write(remaining)
                    staged.flush()
                    os.fsync(staged.fileno())
                current, after = read_pins(parent, path.name, managed)
                if snapshot(before) != snapshot(after) or current != original:
                    raise LifecycleError('Guest trust changed before retirement; no pin was retired')
                visible_parent = path.parent.stat()
                if (original_parent.st_dev, original_parent.st_ino) != (visible_parent.st_dev, visible_parent.st_ino):
                    raise LifecycleError('Guest trust directory changed before retirement')
                os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
        yield retire
    finally:
        if lock is not None:
            os.close(lock)
        os.close(parent)


def delete_guests(scenario):
    guests = manifest_guests(scenario / 'manifest/scenario_vms.json')
    by_id = {guest['vm_id']: guest for guest in guests}
    selected = []
    for row in inventory():
        if row['vm_id'] in by_id:
            if (row.get('vm_name') != by_id[row['vm_id']]['vm_name']
                    or any(row.get(key, False) for key in ('template', 'vm_template', 'is_template'))):
                raise LifecycleError('The selected VMID no longer names the declared non-template guest')
            selected.append(row)
    context = os.environ.get('RANGE42_SOURCE_CONTEXT_DIR', '')
    path = Path(context) / 'ssh_keys/known_hosts' if context else Path.home() / '.ssh/known_hosts'
    targets = ssh_targets(guests, path)
    with locked_pins(path, targets, bool(context)) as retire:
        if selected:
            payload = ''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in selected)
            command(['proxmox_vm.vm_id.stop_force.to.jsons.sh'], data=payload, timeout=600)
            command(['proxmox_vm.vm_id.delete.to.jsons.sh'], data=payload, timeout=600)
        if any(row['vm_id'] in by_id for row in inventory()):
            raise LifecycleError('Native VM absence was not confirmed; no guest pin was retired')
        retire()
    print(':: declared guests are absent; only their exact pins retired; templates and other trust preserved')


def main():
    try:
        if len(sys.argv) != 1:
            raise LifecycleError('Native guest retirement takes no command arguments')
        delete_guests(Path(__file__).resolve().parent)
    except LifecycleError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print('ERROR: Native guest retirement requires review; guest trust was preserved on failure.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
