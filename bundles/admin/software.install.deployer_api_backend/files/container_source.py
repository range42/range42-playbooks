"""Produce an immutable image from the selected checkout for the managed consumer."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


def prepare_request(overrides: dict, source: str, operation: str | None = None) -> dict:
    root = Path(overrides["root"])
    if not root.is_absolute() or root != root.resolve():
        raise ValueError("Installation root must be a canonical absolute path")
    record = root / "installation.json"
    config = {"name": "range42-backend", "uid": 1000, "gid": 1000}
    existing = record.exists() or record.is_symlink()
    if existing:
        info = record.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_mode & 0o077 or info.st_size > 1024 * 1024):
            raise ValueError("Managed record must be a private regular file")
        saved = json.loads(record.read_bytes())
        if saved.get("version") != 1 or saved.get("status") != "ready":
            raise ValueError("Existing installation requires explicit recovery")
        config.update({key: value for key, value in saved["config"].items() if key != "database_host"})
        if config.get("root") != str(root):
            raise ValueError("Managed record belongs to another installation")
    config.update(overrides)
    directory = Path(source)
    if not directory.is_absolute() or not (directory / "Dockerfile").is_file():
        raise ValueError("Selected backend source must contain its canonical Dockerfile")
    # Disable timestamped default attestations: cached identical source must retain
    # the same image ID, including on Docker's containerd image store.
    with tempfile.TemporaryDirectory(prefix="range42-image-") as temporary:
        image_file = Path(temporary) / "image-id"
        command = ["docker", "build", "--target", "runtime", "--iidfile", str(image_file),
                   "--build-arg", f"APP_UID={config['uid']}",
                   "--build-arg", f"APP_GID={config['gid']}", str(directory)]
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=1200,
                           env={**os.environ, "BUILDX_NO_DEFAULT_ATTESTATIONS": "1"})
            image = image_file.read_text().strip()
        except (OSError, subprocess.SubprocessError):
            raise ValueError("Source image build failed; the previous installation is unchanged") from None
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Source build did not produce an immutable image ID")
    config["image"] = image
    # 'update' remains a guarded, idle-only operation. The consumer also handles
    # identical update requests as unchanged without rotating secrets or restarting.
    return {"config": config, "operation": operation or ("update" if existing else "apply")}


def main():
    try:
        data = json.load(sys.stdin)
        result = prepare_request(data["config"], data["source"], data.get("operation"))
        print(json.dumps(result))
    except (ValueError, KeyError, TypeError):
        print(json.dumps({"error": "Source preparation refused; verify source, build and private installation record"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
