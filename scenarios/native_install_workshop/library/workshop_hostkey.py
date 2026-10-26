#!/usr/bin/python
"""Retain and retire only a workshop generation's already authenticated SSH pin."""
import base64
import fcntl
from ipaddress import IPv4Address
import os
from pathlib import Path
import stat
import subprocess
import tempfile


def private(info, mode):
    if info.st_uid != os.geteuid() or info.st_gid != os.getegid() or stat.S_IMODE(info.st_mode) != mode:
        raise ValueError('Host-pin storage must remain private and owned by the controller')


def process(path, action, address, expected, allowed_addresses):
    ip = IPv4Address(address)
    if (not isinstance(allowed_addresses, list) or not 1 <= len(allowed_addresses) <= 20
            or any(str(IPv4Address(value)) != value for value in allowed_addresses)
            or str(ip) not in allowed_addresses):
        raise ValueError('Only a declared workshop endpoint can retire its pin')
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('Host-pin path cannot contain symlinks')
    private(path.parent.stat(), 0o700)
    lock_fd = os.open(path.parent / ('.' + path.name + '.range42-lock'),
                      os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        private(os.fstat(lock_fd), 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            private(info, 0o600)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024 * 1024:
                raise ValueError('Host-pin storage must be a bounded regular file')
            data = os.read(fd, 1024 * 1024 + 1)
        finally:
            os.close(fd)
        lines = data.decode().splitlines(keepends=True)
        # Native enrollment records an exact literal IPv4. Refuse ambiguous,
        # hashed or multi-target matches instead of changing them implicitly.
        result = subprocess.run(['ssh-keygen', '-F', address, '-f', str(path)],
                                capture_output=True, text=True, timeout=5)
        if result.returncode not in (0, 1) or result.stderr:
            raise ValueError('Cannot independently inspect the exact host-pin target')
        matches = [line for line in result.stdout.splitlines() if line and not line.startswith('#')]
        if len(matches) > 1:
            raise ValueError('Multiple host-pin entries need attended review')
        key = None
        if matches:
            fields = matches[0].split()
            if len(fields) != 3 or fields[0] != address or fields[1] != 'ssh-ed25519':
                raise ValueError('Only one native literal Ed25519 pin can be retired')
            try:
                raw = base64.b64decode(fields[2], validate=True)
            except ValueError:
                raise ValueError('Malformed public host key') from None
            if len(raw) != 51 or not raw.startswith(b'\0\0\0\x0bssh-ed25519\0\0\0\x20'):
                raise ValueError('Malformed Ed25519 public host key')
            key = ' '.join(fields[1:])
        if action == 'capture':
            return {'changed': False, 'key': key}
        if key is not None and key != expected:
            raise ValueError('Existing pin differs from the original generation receipt')
        if action == 'check' or key is None:
            return {'changed': False, 'key': key}
        if action != 'remove':
            raise ValueError('Unsupported host-pin action')
        remaining = ''.join(line for line in lines if line.rstrip('\r\n') != matches[0]).encode()
        if remaining == data:
            raise ValueError('The independently inspected pin no longer matches the file')
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.workshop-pin-', delete=False) as handle:
            staged = Path(handle.name)
            try:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(remaining)
                handle.flush()
                os.fsync(handle.fileno())
                assert path.stat().st_ino == info.st_ino and path.read_bytes() == data
                os.replace(staged, path)
            finally:
                staged.unlink(missing_ok=True)
        return {'changed': True, 'key': None}
    finally:
        os.close(lock_fd)


def main():
    from ansible.module_utils.basic import AnsibleModule
    module = AnsibleModule(argument_spec={
        'path': {'type': 'path', 'required': True},
        'action': {'choices': ['capture', 'check', 'remove'], 'required': True},
        'address': {'type': 'str', 'required': True},
        'expected': {'type': 'str', 'default': None},
        'allowed_addresses': {'type': 'list', 'elements': 'str', 'required': True},
    })
    try:
        module.exit_json(**process(**module.params))
    except (ValueError, OSError, AssertionError, subprocess.SubprocessError) as error:
        module.fail_json(msg=str(error))


if __name__ == '__main__':
    main()
