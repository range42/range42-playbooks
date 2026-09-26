"""Render per-VM services using the repositories' existing container contracts."""
from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import secrets

from .plan import PORTS


def node(plan, service):
    return next(vm for vm in plan["vms"] if vm["service"] == service)


def kong_config(plan):
    services = []
    for service, endpoint in plan["endpoints"].items():
        protocol = "https" if service == "wazuh" else "http"
        services.append({"name": service,
                         "url": f"{protocol}://{node(plan, service)['ip']}:{PORTS[service]}",
                         "routes": [{"name": service, "hosts": [endpoint.removeprefix("https://")],
                                     "protocols": ["https"], "strip_path": False,
                                     "preserve_host": True}]})
    return {"_format_version": "3.0", "services": services}


def catalog_compose(plan, service, source):
    """Namespace catalog Compose payloads; reject shared host/global state."""
    doc = copy.deepcopy(source)
    vm = node(plan, service)
    doc["name"] = vm["project_name"]
    for section in ("networks", "volumes"):
        for name, config in doc.get(section, {}).items():
            config = config or {}
            if config.get("external") or config.get("driver_opts"):
                raise ValueError(f"Shared {section} are not allowed: {name}")
            config.pop("name", None)
            doc[section][name] = config
    for name, config in doc["services"].items():
        config.pop("container_name", None)
        if config.get("network_mode") or config.get("privileged") or config.get("external_links"):
            raise ValueError(f"Service {name} bypasses stack isolation")
        ports = []
        for port in config.get("ports", []):
            if not isinstance(port, str):
                raise ValueError("Use short-form catalog ports")
            # Braced defaults may contain a colon, so split at the final separator.
            published, target = port.rsplit(":", 1)
            literal = published if not published.startswith("${") else "variable"
            if ":" in literal:
                raise ValueError("Catalog binds a fixed external address")
            ports.append(f"{vm['ip']}:{published}:{target}")
        if ports:
            config["ports"] = ports
        for volume in config.get("volumes", []):
            if not isinstance(volume, str):
                raise ValueError("Review long-form catalog mounts before use")
            source_path = volume.split(":", 1)[0]
            if source_path.startswith(("/", "~")) and source_path not in {"/etc/timezone", "/etc/localtime"}:
                raise ValueError("Catalog mounts host state")
            if ".." in Path(source_path).parts:
                raise ValueError("Catalog mount escapes its payload")
    return doc


def ensure_credentials(root: Path, stack_id: str, service: str):
    """Create once; never rotate a live stack's encryption key or DB password."""
    if root.is_symlink():
        raise ValueError("Private directory cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    marker = root / "credentials.json"
    if marker.exists():
        if marker.is_symlink() or marker.stat().st_mode & 0o077:
            raise ValueError("Private credentials have unsafe permissions")
        existing = json.loads(marker.read_text())
        if (existing.get("stack_id"), existing.get("service")) != (stack_id, service):
            raise ValueError("Private credentials belong to another stack")
        for name, key in (("api-token", "api_token"), ("credential-key", "credential_key")):
            path = root / name
            if (path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077
                    or path.read_text().strip() != existing[key]):
                raise ValueError("Incomplete credentials; restore the original files before proceeding")
        return existing
    if (root / "api-token").exists() or (root / "credential-key").exists():
        raise ValueError("Partial private credentials; refusing automatic rotation")
    values = {"stack_id": stack_id, "service": service, "api_token": secrets.token_hex(32),
              "credential_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
              "database_password": secrets.token_hex(32), "admin_password": "R42!a" + secrets.token_hex(24),
              "jwt_secret": secrets.token_hex(32), "internal_token": secrets.token_hex(32)}
    for name, content in (("api-token", values["api_token"]), ("credential-key", values["credential_key"]),
                          ("credentials.json", json.dumps(values))):
        fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content + "\n")
    return values
