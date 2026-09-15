"""Container installer state primitives; never print or silently rotate secrets."""
from __future__ import annotations

import base64
import binascii
import fcntl
import os
from pathlib import Path
import secrets
import stat


def _secret(path: Path) -> str | None:
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        raise ValueError("Credential paths must be regular files, without symbolic links")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
            raise ValueError("Credential paths must be bounded regular files")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            try:
                value = stream.read(4097).decode("ascii").strip()
            except UnicodeError:
                raise ValueError("Credential files must contain valid ASCII credentials") from None
    finally:
        os.close(descriptor)
    if path.name == "api-token":
        if len(value) < 32 or any(character.isspace() for character in value):
            raise ValueError("Existing API token is invalid; restore the original credentials")
    else:
        try:
            decoded = base64.b64decode(value.encode(), altchars=b"-_", validate=True)
        except (binascii.Error, ValueError):
            decoded = b""
        if len(decoded) != 32:
            raise ValueError("Existing encryption key is invalid; restore the original credentials")
    return value


def provision_credentials(directory: Path, database: Path, *, uid: int, gid: int) -> None:
    directory = directory.absolute()
    if directory != directory.resolve():
        raise ValueError("Credential directory cannot contain symbolic links")
    paths = [directory / name for name in ("api-token", "credential-key")]
    values = [_secret(path) for path in paths]
    if database.exists() and any(value is None for value in values):
        raise ValueError("Existing database requires its original API and encryption credentials")
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        # Serialize concurrent first-install retries without leaving a secret lock file.
        values = [_secret(path) for path in paths]
        if database.exists() and any(value is None for value in values):
            raise ValueError("Existing database requires its original API and encryption credentials")
        for path, value in zip(paths, values, strict=True):
            if value is None:
                value = (secrets.token_hex(32) if path.name == "api-token"
                         else base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w") as stream:
                    stream.write(value + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            path.chmod(0o600)
            os.chown(path, uid, gid, follow_symlinks=False)
        os.fchmod(descriptor, 0o700)
        os.fchown(descriptor, uid, gid)
    finally:
        os.close(descriptor)
