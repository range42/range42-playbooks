"""Installer-owned idle probe; admission is continuously fenced by the host.

Executed inside the exact installed container using its backend validators.
This is not a standalone replacement for app.core.maintenance_guard: the host
must own the bound admission inode before starting this probe and until cutover.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys

from app.core.config import settings
from app.core.locks import ProvisioningLock
from app.core.maintenance import MaintenanceGate, PROTOCOL
from app.core.maintenance_guard import _proof_matches, assert_idle


def require_external_fence(gate):
    descriptor = gate._open()
    try:
        if os.fstat(descriptor).st_size:
            raise ValueError('Unfinished maintenance intent requires explicit recovery')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        raise ValueError('Host admission fence is missing')
    finally:
        os.close(descriptor)


@contextmanager
def held_idle(proof):
    prefix = 'sqlite+aiosqlite:///'
    if not settings.db_url.startswith(prefix) or '?' in settings.db_url:
        raise ValueError('Maintenance requires an absolute installed SQLite database')
    database = Path(settings.db_url.removeprefix(prefix))
    workspace = settings.workspace_root
    if (not database.is_absolute() or database != database.resolve() or not database.is_file()
            or workspace != workspace.resolve() or not workspace.is_dir()
            or not settings.maintenance_lock_file):
        raise ValueError('Installed database or workspace binding cannot be verified')
    gate = MaintenanceGate(Path(settings.maintenance_lock_file))
    _proof_matches(proof, gate)
    require_external_fence(gate)
    locks = workspace / '.locks'
    if locks != locks.resolve():
        raise ValueError('Provisioning lock cannot contain symbolic links')
    with ProvisioningLock(locks):
        db = sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=1)
        try:
            db.execute('BEGIN IMMEDIATE')
            assert_idle(db, workspace)
            _proof_matches(proof, gate)
            require_external_fence(gate)
            yield
        finally:
            db.rollback()
            db.close()


def main():
    try:
        line = sys.stdin.buffer.readline(4097)
        if len(line) > 4096 or not line.endswith(b'\n'):
            raise ValueError('Maintenance proof is not bounded')
        proof = json.loads(line)
        with held_idle(proof):
            print(json.dumps({'status': 'idle', 'protocol': PROTOCOL,
                              'process': proof['process'], 'lock': proof['lock']}), flush=True)
            sys.stdin.buffer.read(1)
    except Exception:
        print(json.dumps({'status': 'refused'}), flush=True)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
