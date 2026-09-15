"""Validate a managed installation and render its explicit Compose contract."""

from __future__ import annotations

import ipaddress
import hashlib
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

_FIELDS = {
    "root",
    "name",
    "image",
    "uid",
    "gid",
    "state_dir",
    "workspace_host",
    "workspace_container",
    "database_container",
    "secrets_dir",
    "port",
    "listen_address",
    "cors_origins",
    "git_allowed_hosts",
    "runtime_dir",
    "workspace_template_dir",
    "runtime_container",
    "runtime_config_container",
    "runtime_ca_container",
    "workspace_template_container",
    "network_mode",
    "inventory_container",
    "vault_password_host",
    "vault_password_container",
}
STATE_CONTAINER = Path("/var/lib/range42")


def host_path(value: str) -> str:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("Host bindings must be absolute paths")
    path = Path(value)
    if path != path.resolve():
        raise ValueError(
            "Host bindings cannot contain symbolic links or unresolved path segments"
        )
    return str(path)


def container_path(value: str) -> Path:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value)
        or value.startswith("//")
        or ".." in Path(value).parts
        or str(Path(value)) != value
    ):
        raise ValueError("Container bindings must be canonical absolute paths")
    return Path(value)


def overlaps(left: Path, right: Path) -> bool:
    return left.is_relative_to(right) or right.is_relative_to(left)


def vault_password_digest(plan):
    """Hash an existing private file without following links or executing it."""
    if not plan.get("vault_password_host"):
        return None
    descriptor = None
    directory = None
    try:
        path = Path(host_path(plan["vault_password_host"]))
        secrets = Path(host_path(plan["secrets_dir"]))
        if (
            not path.is_relative_to(secrets)
            or path == secrets
            or path in (secrets / "api-token", secrets / "credential-key")
        ):
            raise ValueError("Vault password must be separate from API credentials")
        directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) not in (0o400, 0o600)
            or (before.st_uid, before.st_gid) != (plan["uid"], plan["gid"])
            or not 0 < before.st_size <= 4096
        ):
            raise ValueError("Vault password must be a private owned regular file")
        data = os.read(descriptor, 4097)
        after = os.fstat(descriptor)
        current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (
            len(data) != before.st_size
            or not data.strip()
            or any(getattr(before, key) != getattr(after, key) for key in fields)
            or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise ValueError("Vault password changed during verification")
        return hashlib.sha256(data).hexdigest()
    except (OSError, ValueError):
        raise ValueError("Vault password file is missing, unsafe or changed") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory is not None:
            os.close(directory)


def vault_layout(raw, secrets_dir, layout, runtime, uid, gid):
    source = raw.get("vault_password_host", "")
    target = raw.get("vault_password_container", "")
    if (
        not isinstance(source, str)
        or not isinstance(target, str)
        or bool(source) != bool(target)
    ):
        raise ValueError(
            "Vault password host and container file bindings must be paired"
        )
    if not source:
        return {"vault_password_host": "", "vault_password_container": ""}
    try:
        source = host_path(source)
        destination = container_path(target)
    except ValueError:
        raise ValueError("Vault password file bindings must be canonical") from None
    if destination.parent not in (
        Path("/run/secrets"),
        Path("/etc/range42/secrets"),
    ) or destination.name in (
        "api-token",
        "api_token",
        "credential-key",
        "credential_key",
    ):
        raise ValueError("Vault password needs a separate dedicated secrets filename")
    if runtime:
        protected = [
            Path(layout["runtime_container"]),
            Path(layout["workspace_template_container"]),
            Path(layout["runtime_config_container"]) / "ansible.cfg",
            Path(layout["runtime_config_container"]) / "bundle-runtime.json",
            Path(layout["runtime_ca_container"]),
        ]
        if any(overlaps(destination, path) for path in protected):
            raise ValueError("Vault password cannot overlap runtime or template mounts")
    result = {"vault_password_host": source, "vault_password_container": target}
    vault_password_digest(
        {**result, "secrets_dir": secrets_dir, "uid": uid, "gid": gid}
    )
    return result


def runtime_layout(raw, runtime, template, state, workspace, secrets_dir, inside):
    destination = container_path(raw.get("runtime_container", "/runtime"))
    configuration = container_path(
        raw.get("runtime_config_container", str(destination))
    )
    ca = container_path(
        raw.get("runtime_ca_container", str(destination / "proxmox-ca.pem"))
    )
    private = container_path(
        raw.get("workspace_template_container", "/run/range42-template")
    )
    if not runtime and (destination, configuration, ca, private) != (
        Path("/runtime"),
        Path("/runtime"),
        Path("/runtime/proxmox-ca.pem"),
        Path("/run/range42-template"),
    ):
        raise ValueError(
            "Nondefault runtime layout requires both runtime and private template sources"
        )
    if not (
        destination.is_relative_to("/runtime")
        or (
            destination.is_relative_to("/opt")
            and destination != Path("/opt")
            and not overlaps(destination, Path("/opt/venv"))
        )
    ):
        raise ValueError(
            "Runtime container root must use a dedicated /runtime or /opt directory"
        )
    if configuration != destination and (
        not configuration.is_relative_to("/etc/range42")
        or overlaps(configuration, destination)
    ):
        raise ValueError(
            "External runtime configuration must use a directory under /etc/range42"
        )
    if ca != destination / "proxmox-ca.pem" and not any(
        ca.is_relative_to(parent) and ca != Path(parent)
        for parent in ("/etc/ssl/certs", "/etc/range42")
    ):
        raise ValueError(
            "External runtime CA must use a file under /etc/ssl/certs or /etc/range42"
        )
    if not any(
        private.is_relative_to(parent) and private != Path(parent)
        for parent in ("/run", "/etc/range42")
    ):
        raise ValueError(
            "Private template must use a dedicated /run or /etc/range42 directory"
        )
    targets = [(destination, "runtime"), (private, "template")]
    if configuration != destination:
        targets += [
            (configuration / "ansible.cfg", "config"),
            (configuration / "bundle-runtime.json", "profile"),
        ]
    if ca != destination / "proxmox-ca.pem":
        targets.append((ca, "CA"))
    protected = [STATE_CONTAINER, inside, Path("/run/secrets")]
    for position, (path, _) in enumerate(targets):
        if any(overlaps(path, reserved) for reserved in protected):
            raise ValueError(
                "Runtime mounts cannot overlap writable state or API credentials"
            )
        if any(overlaps(path, other) for other, _ in targets[:position]):
            raise ValueError(
                "Runtime, config, CA and private template mounts cannot overlap"
            )
    if runtime:
        sources = [Path(runtime), Path(template)]
        if overlaps(*sources) or any(
            overlaps(source, Path(writable))
            for source in sources
            for writable in (state, workspace, secrets_dir)
        ):
            raise ValueError(
                "Read-only runtime and private template sources cannot overlap writable state or credentials"
            )
    return {
        "runtime_container": str(destination),
        "runtime_config_container": str(configuration),
        "runtime_ca_container": str(ca),
        "workspace_template_container": str(private),
    }


def validate_config(raw: dict) -> dict:
    if not isinstance(raw, dict) or set(raw) - _FIELDS:
        raise ValueError("Unknown installer configuration fields")
    for key in ("root", "name", "image", "uid", "gid"):
        if key not in raw:
            raise ValueError("Missing required installer configuration")
    root = host_path(raw["root"])
    if not isinstance(raw["name"], str) or not re.fullmatch(
        "[a-z][a-z0-9-]{0,31}", raw["name"]
    ):
        raise ValueError("Installation name must be a short lowercase identifier")
    if not isinstance(raw["image"], str) or not re.fullmatch(
        r"(?:sha256:|[a-zA-Z0-9./:_-]+@sha256:)[0-9a-f]{64}", raw["image"]
    ):
        raise ValueError("Use an immutable image ID or repository digest")
    for key in ("uid", "gid"):
        if type(raw[key]) is not int or not 0 <= raw[key] < 2**31:
            raise ValueError("Image UID and GID must be explicit integers")
    port = raw.get("port", 8000)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Listener port must be between 1 and 65535")
    address = str(ipaddress.ip_address(raw.get("listen_address", "127.0.0.1")))
    network_mode = raw.get("network_mode", "bridge")
    if network_mode not in ("bridge", "host"):
        raise ValueError("Network mode must be explicit bridge or host")
    state = host_path(raw.get("state_dir", root + "/state"))
    workspace = host_path(raw.get("workspace_host", state + "/workspaces"))
    secrets_dir = host_path(raw.get("secrets_dir", root + "/secrets"))
    for writable in (Path(state), Path(workspace)):
        if (
            Path(root).is_relative_to(writable)
            or Path(secrets_dir).is_relative_to(writable)
            or writable.is_relative_to(secrets_dir)
        ):
            raise ValueError(
                "Writable mounts cannot overlap installer records or credentials"
            )
    inside = container_path(
        raw.get("workspace_container", "/var/lib/range42/workspaces")
    )
    if not (
        inside.is_relative_to(STATE_CONTAINER / "workspaces")
        or (inside.is_relative_to("/home") and inside != Path("/home"))
    ):
        raise ValueError(
            "Workspace container binding must use persistent workspace or legacy home paths"
        )
    database = container_path(
        raw.get("database_container", str(inside / ".range42.db"))
    )
    if (
        database in (STATE_CONTAINER, inside)
        or ".locks" in database.parts
        or database.is_relative_to(STATE_CONTAINER / "home")
        or any(
            database.is_relative_to(STATE_CONTAINER / ("maintenance.lock" + suffix))
            for suffix in ("", "-wal", "-shm")
        )
    ):
        raise ValueError(
            "Database cannot replace reserved state, maintenance or workspace paths"
        )
    if database.is_relative_to(inside):
        database_host = Path(workspace) / database.relative_to(inside)
    elif database.is_relative_to(STATE_CONTAINER) and not inside.is_relative_to(
        database
    ):
        database_host = Path(state) / database.relative_to(STATE_CONTAINER)
    else:
        raise ValueError(
            "Database must remain inside the explicitly mapped state or workspace"
        )
    host_path(str(database_host))
    if database_host.exists() and not stat.S_ISREG(database_host.lstat().st_mode):
        raise ValueError("Existing database must be an ordinary file")
    inventory = raw.get("inventory_container", "")
    if inventory != "":
        inventory = container_path(inventory)
        if (
            not (
                inventory.is_relative_to(inside)
                or inventory.is_relative_to(STATE_CONTAINER)
            )
            or inventory in (STATE_CONTAINER, inside)
            or ".locks" in inventory.parts
            or inventory.is_relative_to(STATE_CONTAINER / "home")
            or any(
                overlaps(inventory, STATE_CONTAINER / ("maintenance.lock" + suffix))
                for suffix in ("", "-wal", "-shm")
            )
            or overlaps(inventory, database)
        ):
            raise ValueError(
                "Inventory must use a dedicated mapped state or workspace directory without reserved path overlap"
            )
        inventory = str(inventory)
    origins = raw.get("cors_origins", [])
    if not isinstance(origins, list):
        raise ValueError("CORS origins must be an explicit list")
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("CORS requires exact HTTP origins without paths")
    forges = raw.get("git_allowed_hosts", ["github.com", "gitlab.com", "codeberg.org"])
    if (
        not isinstance(forges, list)
        or not forges
        or any(
            not isinstance(host, str)
            or not re.fullmatch("[a-zA-Z0-9.-]+(?::[0-9]+)?", host)
            for host in forges
        )
    ):
        raise ValueError("Git hosts must be explicit DNS names with optional ports")
    runtime = host_path(raw["runtime_dir"]) if raw.get("runtime_dir") else None
    template = (
        host_path(raw["workspace_template_dir"])
        if raw.get("workspace_template_dir")
        else None
    )
    if bool(runtime) != bool(template):
        raise ValueError(
            "Execution runtime and private workspace template must be configured together"
        )
    layout = runtime_layout(
        raw, runtime, template, state, workspace, secrets_dir, inside
    )
    vault = vault_layout(raw, secrets_dir, layout, runtime, raw["uid"], raw["gid"])
    return {
        "root": root,
        "name": raw["name"],
        "image": raw["image"],
        "uid": raw["uid"],
        "gid": raw["gid"],
        "state_dir": state,
        "workspace_host": workspace,
        "workspace_container": str(inside),
        "database_container": str(database),
        "database_host": str(database_host),
        "secrets_dir": secrets_dir,
        "port": port,
        "listen_address": address,
        "cors_origins": origins,
        "git_allowed_hosts": forges,
        "runtime_dir": runtime,
        "workspace_template_dir": template,
        "network_mode": network_mode,
        "inventory_container": inventory,
        **layout,
        **vault,
    }


def compose_document(plan: dict, release: str) -> dict:
    def bind(source, target, readonly=False):
        return {
            "type": "bind",
            "source": source,
            "target": target,
            "read_only": readonly,
            "bind": {"create_host_path": False},
        }

    environment = {
        "HOME": "/var/lib/range42/home",
        "RANGE42_AUTH_MODE": "required",
        "RANGE42_WORKSPACE_ROOT": plan["workspace_container"],
        "RANGE42_DB_URL": "sqlite+aiosqlite:///" + plan["database_container"],
        "RANGE42_API_TOKEN_FILE": "/run/secrets/api_token",
        "RANGE42_CREDENTIAL_KEY_FILE": "/run/secrets/credential_key",
        "RANGE42_MAINTENANCE_LOCK_FILE": "/var/lib/range42/maintenance.lock",
        "RANGE42_CORS_ORIGINS": ",".join(plan["cors_origins"]),
        "RANGE42_GIT_ALLOWED_HOSTS": ",".join(plan["git_allowed_hosts"]),
    }
    mounts = [
        bind(plan["state_dir"], str(STATE_CONTAINER)),
        bind(plan["workspace_host"], plan["workspace_container"]),
        bind(plan["secrets_dir"] + "/api-token", "/run/secrets/api_token", True),
        bind(
            plan["secrets_dir"] + "/credential-key", "/run/secrets/credential_key", True
        ),
    ]
    if plan.get("inventory_container"):
        environment["API_BACKEND_INVENTORY_DIR"] = plan["inventory_container"]
    if plan.get("vault_password_host"):
        environment["VAULT_PASSWORD_FILE"] = plan["vault_password_container"]
        mounts.append(
            bind(plan["vault_password_host"], plan["vault_password_container"], True)
        )
    if plan["runtime_dir"]:
        runtime = Path(plan.get("runtime_container", "/runtime"))
        configuration = Path(plan.get("runtime_config_container", str(runtime)))
        ca = Path(plan.get("runtime_ca_container", str(runtime / "proxmox-ca.pem")))
        template = plan.get("workspace_template_container", "/run/range42-template")
        mounts += [
            bind(plan["runtime_dir"], str(runtime), True),
            bind(plan["workspace_template_dir"], template, True),
        ]
        if configuration != runtime:
            mounts += [
                bind(
                    str(Path(plan["runtime_dir"]) / name),
                    str(configuration / name),
                    True,
                )
                for name in ("ansible.cfg", "bundle-runtime.json")
            ]
        if ca != runtime / "proxmox-ca.pem":
            mounts.append(
                bind(str(Path(plan["runtime_dir"]) / "proxmox-ca.pem"), str(ca), True)
            )
        environment.update(
            {
                "API_BACKEND_PUBLIC_PLAYBOOKS_DIR": str(runtime / "range42-playbooks"),
                "API_BACKEND_WWWAPP_PLAYBOOKS_DIR": str(runtime / "range42-playbooks"),
                "RANGE42_BUNDLE_DIR": str(runtime / "range42-playbooks/bundles"),
                "RANGE42_BUNDLE_RUNTIME_MANIFEST": str(
                    configuration / "bundle-runtime.json"
                ),
                "RANGE42_WORKSPACE_TEMPLATE_DIR": template,
                "RANGE42_PROXMOX_CA_FILE": str(ca),
                "RANGE42_INVENTORY__DOCKER__CTF": str(
                    runtime / "range42-catalog/03_container_layer/docker/_ctf"
                ),
                "ANSIBLE_CONFIG": str(configuration / "ansible.cfg"),
                "ANSIBLE_COLLECTIONS_PATH": str(runtime / "collections"),
                "ANSIBLE_ROLES_PATH": ":".join(
                    str(runtime / path)
                    for path in (
                        "range42-ansible_roles-proxmox_controller/roles",
                        "range42-catalog/02_ansible_layer/admin/roles",
                        "range42-catalog/02_ansible_layer/trainee/roles",
                        "range42/roles",
                    )
                ),
            }
        )
    service = {
        "image": plan["image"],
        "pull_policy": "never",
        "init": True,
        "container_name": plan["name"] + "-" + release[:16],
        "labels": {
            "org.range42.installation": plan["root"],
            "org.range42.release": release,
        },
        "user": f"{plan['uid']}:{plan['gid']}",
        "environment": environment,
        "volumes": mounts,
        "ports": [
            {
                "target": 8000,
                "published": str(plan["port"]),
                "host_ip": plan["listen_address"],
                "protocol": "tcp",
            }
        ],
        "read_only": True,
        "tmpfs": ["/tmp:mode=1777,size=256m"],
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "stop_grace_period": "60s",
        "restart": "unless-stopped",
    }
    if plan.get("network_mode", "bridge") == "host":
        service.pop("ports")
        service["network_mode"] = "host"
        service["command"] = [
            "uvicorn",
            "app.main:app",
            "--host",
            plan["listen_address"],
            "--port",
            str(plan["port"]),
            "--workers",
            "1",
            "--log-level",
            "info",
        ]
        address = plan["listen_address"]
        address = (
            "127.0.0.1"
            if address == "0.0.0.0"
            else "::1"
            if address == "::"
            else address
        )
        host = "[" + address + "]" if ":" in address else address
        url = f"http://{host}:{plan['port']}/v1/health"
        service["healthcheck"] = {
            "test": [
                "CMD",
                "python",
                "-c",
                f"import urllib.request; urllib.request.urlopen({url!r}, timeout=3).close()",
            ],
            "interval": "30s",
            "timeout": "5s",
            "start_period": "20s",
            "retries": 3,
        }
    return {"services": {"api": service}}
