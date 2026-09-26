"""Prepare instance configuration for the shared installers; register the child API.

Private staging is persistent controller state. Application deployment remains
in the existing Ansible bundles and application-owned Compose files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import ssl
import urllib.request

import yaml

from .render import catalog_compose, ensure_credentials, kong_config, node


def private_write(path, text, mode=0o600):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlink")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "w") as stream:
        stream.write(text)
    path.chmod(mode)


def validate_template(root, stack_id):
    root = Path(root)
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("Use a private dedicated credential template directory")
    paths = list(root.rglob("*"))
    if len(paths) > 300:
        raise ValueError("Credential template is too large")
    for path in paths:
        if path.is_symlink() or path.stat().st_mode & 0o077 or not (path.is_dir() or path.is_file()):
            raise ValueError("Credential template contains links, special files or unsafe permissions")
        if path.is_file() and path.stat().st_size > 1048576:
            raise ValueError("Credential template file exceeds 1 MiB")
    if json.loads((root / "stack.json").read_text()).get("stack_id") != stack_id:
        raise ValueError("Credential template belongs to another stack")
    if not (root / "secrets/default_vault.yml").read_text().startswith("$ANSIBLE_VAULT;"):
        raise ValueError("Dedicated template must contain an encrypted Ansible vault")
    if not (root / "secrets/vault_pass.txt").read_text().strip():
        raise ValueError("Dedicated vault password is missing")


def validate_target_permissions(permissions, allowed_paths):
    """Check the child token's effective ACLs, not a user-supplied scope label."""
    if not allowed_paths or any(not re.fullmatch(r"/(?:pool|vms|storage|nodes|sdn)/[^/]+(?:/[^/]+)*", p)
                                or ".." in p.split("/") for p in allowed_paths):
        raise ValueError("Declare specific child target permission paths")
    forbidden = {"Permissions.Modify", "User.Modify", "Group.Allocate", "Realm.Allocate",
                 "Sys.Modify", "Sys.PowerMgmt", "Sys.Console", "Pool.Allocate"}
    if not isinstance(permissions, dict) or not permissions:
        raise ValueError("The child token has no verifiable effective permissions")
    for path, privileges in permissions.items():
        enabled = {key for key, value in privileges.items() if value}
        if enabled and (not any(path == p or path.startswith(p + "/") for p in allowed_paths)
                        or enabled & forbidden):
            raise ValueError("Child token has privileges outside the declared isolated target")


def catalog_environment(plan, service, credentials):
    domain = plan["endpoints"][service].removeprefix("https://")
    env = {"POSTGRES_PASSWORD": credentials["database_password"], "HTTP_PORT": str(
        {"gitea": 3000, "registry": 3000, "mattermost": 8065, "rocketchat": 3000, "nextcloud": 8080}[service])}
    if service in {"gitea", "registry"}:
        env.update({"GITEA_DOMAIN": domain, "GITEA_BASE_URL": "https://" + domain,
                    "GITEA_ADMIN_USER": "range42-admin", "GITEA_ADMIN_PASS": credentials["admin_password"],
                    "GITEA_SECRET_KEY": credentials["jwt_secret"], "GITEA_INTERNAL_TOKEN": credentials["internal_token"]})
    else:
        prefix = {"mattermost": "MM", "nextcloud": "NC", "rocketchat": "RC"}[service]
        env.update({f"{prefix}_BASE_URL": "https://" + domain, f"{prefix}_DOMAIN": domain,
                    f"{prefix}_ADMIN_USER": "range42-admin", f"{prefix}_ADMIN_PASS": credentials["admin_password"],
                    f"{prefix}_ADMIN_EMAIL": "admin@" + plan["domain"]})
    return env


def catalog_users(plan, service, credentials):
    return {"admins": [{"username": "range42-admin", "email": "admin@" + plan["domain"],
                         "password": credentials["admin_password"], "name": "Range42 administrator",
                         "ssh_keys": []}], "users": []}


def env_text(values):
    # Single quotes stop Compose from expanding bcrypt's dollar signs.
    if any("\n" in str(v) or "'" in str(v) for v in values.values()):
        raise ValueError("Unsafe environment value")
    return "".join(f"{key}='{value}'\n" for key, value in values.items())


def claim_node(plan, service, root):
    node(plan, service)
    root = Path(root)
    if root.is_symlink():
        raise ValueError("Node root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = {"stack_id": plan["id"], "service": service,
                "plan_sha256": hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()}
    marker = root / "owner.json"
    if marker.exists() and json.loads(marker.read_text()) != identity:
        raise ValueError("Installation belongs to a different plan; use an explicit migration")
    credentials = ensure_credentials(root / "private", plan["id"], service)
    private_write(marker, json.dumps(identity))
    return credentials


def prepare_node(plan, service, root):
    root = Path(root)
    if service in {"backend", "cli"}:
        validate_template(root / "template", plan["id"])
    credentials = claim_node(plan, service, root)
    if service == "wazuh":
        private_write(root / "private/wazuh.yml", yaml.safe_dump({
            "infrastructure_wazuh_admin_password": credentials["admin_password"],
            "indexer_admin_password": credentials["admin_password"],
            "dashboard_password": credentials["database_password"],
            "indexer_security_password": credentials["admin_password"],
            "platform_wazuh_api_password": "R42!a" + credentials["internal_token"][:48],
            "wazuh_api_credentials": [{"id": "default", "url": "https://127.0.0.1", "port": 55000,
                "username": "wazuh-wui", "password": "R42!a" + credentials["internal_token"][:48]}],
        }))
        return
    if service in {"gitea", "registry", "mattermost", "nextcloud", "rocketchat"}:
        compose = catalog_compose(plan, service, yaml.safe_load((root / "source/compose.yml").read_text()))
        # Catalog build contexts/mounts stay beneath the private copied payload.
        for config in compose["services"].values():
            if "build" in config:
                if isinstance(config["build"], str):
                    config["build"] = {"context": "./source"}
                else:
                    config["build"]["context"] = "./source"
            config["volumes"] = ["./source/" + value[2:] if value.startswith("./") else value
                                 for value in config.get("volumes", [])]
            if config.get("env_file"):
                config["env_file"] = ["./private/catalog.env"]
        private_write(root / "private/catalog.env", env_text(catalog_environment(plan, service, credentials)))
        # Mount credentials at runtime; never bake provisioned passwords into a Docker image.
        private_write(root / "private/users.yml", yaml.safe_dump(catalog_users(plan, service, credentials)))
        private_write(root / "source/provisioning/users.yml", "admins: []\nusers: []\n", 0o644)
        if "provisioner" in compose["services"]:
            compose["services"]["provisioner"].setdefault("volumes", []).append(
                "./private/users.yml:/provisioning/users.yml:ro")
        if service == "rocketchat":
            # The catalog's health condition waits for a replica set that this job creates.
            compose["services"]["mongo-init-replica"]["depends_on"]["mongodb"] = {"condition": "service_started"}
        if service == "nextcloud":
            compose["services"]["nextcloud"]["environment"].update({
                "OVERWRITEPROTOCOL": "https", "TRUSTED_PROXIES": node(plan, "gateway")["ip"]})
        private_write(root / "compose.yml", yaml.safe_dump(compose, sort_keys=False), 0o644)
        # The existing catalog role invokes Compose with its standard .env.
        private_write(root / ".env", env_text(catalog_environment(plan, service, credentials)))
    if service == "gateway":
        private_write(root / "kong.yml", yaml.safe_dump(kong_config(plan), sort_keys=False), 0o644)
    elif service == "ui":
        private_write(root / "config.json", json.dumps({"defaultBackendUrl": plan["endpoints"]["backend"],
                                                       "defaultNodeName": plan["node"]}), 0o644)
    elif service == "backend":
        remote = node(plan, service)["install_root"]
        private_write(root / "private/backend.env", env_text({
            "RANGE42_CONTAINER_IMAGE": node(plan, service)["project_name"] + ":installed",
            "RANGE42_LISTEN_ADDRESS": node(plan, service)["ip"],
            "RANGE42_CONTAINER_PORT": "8000", "RANGE42_CONTAINER_SECRETS_DIR": remote + "/private",
            "RANGE42_RUNTIME_DIR": remote + "/runtime", "RANGE42_WORKSPACE_TEMPLATE_DIR": remote + "/template",
            "RANGE42_CORS_ORIGINS": plan["endpoints"]["ui"],
            "RANGE42_TRUSTED_PROXY_IPS": node(plan, "gateway")["ip"],
        }))
    elif service == "reporting":
        import bcrypt
        postgres = {"POSTGRES_USER": "reporting", "POSTGRES_DB": "reporting",
                    "POSTGRES_PASSWORD": credentials["database_password"]}
        private_write(root / "private/postgres.env", env_text(postgres))
        password_hash = root / "private/reporting-admin.hash"
        if not password_hash.exists():
            private_write(password_hash, bcrypt.hashpw(credentials["admin_password"].encode(), bcrypt.gensalt()).decode())
        private_write(root / "private/reporting.env", env_text({
            "DATABASE_URL": f"postgresql+asyncpg://reporting:{credentials['database_password']}@postgres:5432/reporting",
            "JWT_SECRET": credentials["jwt_secret"], "STORAGE_BACKEND": "local",
            "STORAGE_LOCAL_PATH": "/data/attachments", "RUN_MIGRATIONS_ON_START": "false",
            "CORS_ORIGINS": plan["endpoints"]["reporting"], "SESSION_HTTPS_ONLY": "true",
            "EMERGENCY_ADMIN_ENABLED": "true", "EMERGENCY_ADMIN_PASSWORD_HASH": password_hash.read_text(),
        }))
        deploy = root / "source/range42-reporting-tool/deploy"
        private_write(deploy / ".env", (root / "private/reporting.env").read_text())
        # TLS terminates at Kong; keep the application's Caddy routes.
        caddy = deploy / "Caddyfile"
        if caddy.exists():
            private_write(caddy, caddy.read_text().replace("\ttls {$TLS_CONFIG}\n", ""), 0o644)
        private_write(root / "private/compose.env", env_text({"DOMAIN": ":80"}))
        override = {"services": {
            "postgres": {"environment": {"POSTGRES_PASSWORD": credentials["database_password"]}},
            "caddy": {"ports": [node(plan, service)["ip"] + ":80:80"],
                      "depends_on": {"frontend": {"condition": "service_completed_successfully"}}},
        }}
        # Compose !override replaces the production edge ports rather than appending.
        text = yaml.safe_dump(override, sort_keys=False).replace("    ports:", "    ports: !override")
        private_write(root / "reporting.override.yml", text)



def request_json(url, token, body=None, context=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        return json.load(response)


def validate_cli_workload(template):
    """The child CLI gets an explicit workload, never the parent's management scenario."""
    template = Path(template)
    try:
        config = json.loads((template / 'cli.json').read_text())
        label = config['scenario']
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', label):
            raise ValueError()
        workload = template / 'workload'
        for name in ('main.yml', 'hosts.yml', 'templates/ansible-inventory.j2', 'templates/ssh-config.j2'):
            path = workload / name
            if not path.is_file() or path.is_symlink() or not path.read_text().strip():
                raise ValueError()
        inventory = yaml.safe_load((workload / 'hosts.yml').read_text())
        def has_hosts(group):
            return isinstance(group, dict) and (bool(group.get('hosts')) or any(
                has_hosts(child) for child in group.get('children', {}).values()))
        if not has_hosts(inventory.get('all', {})):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('CLI requires cli.json and a reviewed workload with inventory and SSH templates') from None
    return label


def native_wrappers(scenario):
    """Thin entry scripts consumed by the shared range42-context dispatcher."""
    scenario = Path(scenario)
    for suffix, playbook in {'setup.sh': 'main.yml', 'setup_vms_only.sh': 'main_vms_only.yml',
                            'configure.sh': 'configure.yml', 'delete_all.sh': 'teardown.yml'}.items():
        target = scenario / (scenario.name + '.' + suffix)
        if (scenario / playbook).is_file() and not target.exists():
            private_write(target, '#!/bin/sh\nset -eu\ncd -- "$(dirname -- "$0")"\n'
                'exec ansible-playbook -i "${RANGE42_ANSIBLE_ROLES__INVENTORY_DIR:?}/inventory_default.yml" '
                '--vault-password-file "${RANGE42_VAULT_PASSWORD_FILE:?}" ' + playbook + ' "$@"\n', 0o700)


def bootstrap_cli(plan, state, template, runtime, *, workspace_base=None):
    """Initialize the CLI's own writable workspace without touching the API's state."""
    state, template, runtime = Path(state), Path(template), Path(runtime)
    label = validate_cli_workload(template)
    workspace = Path(workspace_base or state / "workspaces") / (plan["id"] + "-" + label)
    home = state / "home"
    for path in (workspace, workspace / "inventory", workspace / "bin", home / ".ssh"):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Match backend inheritance: an existing credential set is never mixed with a new template.
    if not (workspace / "secrets").exists() and not (workspace / "ssh_keys").exists():
        for name in ("secrets", "ssh_keys"):
            if (template / name).is_dir():
                shutil.copytree(template / name, workspace / name)
    for path in workspace.rglob("*"):
        if not path.is_symlink():
            path.chmod(0o700 if path.is_dir() else 0o600)
    scenario = runtime / 'range42-playbooks/scenarios' / label
    if scenario.exists():
        if not (scenario / '.range42-stack-owner').is_file() or (scenario / '.range42-stack-owner').read_text() != plan['id']:
            raise ValueError('CLI workload would overwrite an unrelated scenario')
    shutil.copytree(template / 'workload', scenario, dirs_exist_ok=True)
    private_write(scenario / '.range42-stack-owner', plan['id'])
    native_wrappers(scenario)
    link = workspace / 'scenario'
    if link.is_symlink() and link.resolve() != scenario.resolve():
        raise ValueError('CLI workspace points at another scenario')
    if not link.exists():
        link.symlink_to(scenario, target_is_directory=True)
    ca_bundle = workspace / 'ca-bundle.pem'
    ca_sources = (Path(ssl.get_default_verify_paths().openssl_cafile), runtime / 'proxmox-ca.pem')
    private_write(ca_bundle, '\n'.join(path.read_text() for path in ca_sources if path.is_file()))
    environment = {
        "RANGE42_INFRASTRUCTURE_CODENAME": plan["id"], "RANGE42_INFRASTRUCTURE_LAB": label,
        "RANGE42_ACTIVE_WORKSPACE": workspace.name, "RANGE42_ACTIVE_CONFIG_DIR": str(workspace),
        "RANGE42_CONFIG__ROOT_DIR": str(workspace), "RANGE42_CONFIG_BASE_DIR": str(workspace.parent),
        "RANGE42_GITDIR__ROOT_DIR": str(runtime), "RANGE42_INVENTORY": str(runtime / "range42-catalog"),
        "RANGE42_BUNDLE_DIR": str(runtime / "range42-playbooks/bundles"),
        "RANGE42_VAULT_PASSWORD_FILE": str(workspace / "secrets/vault_pass.txt"),
        "ANSIBLE_VAULT_PASSWORD_FILE": str(workspace / "secrets/vault_pass.txt"),
        "ANSIBLE_INVENTORY": str(workspace / "inventory/inventory_default.yml"),
        "RANGE42_ANSIBLE_ROLES__INVENTORY_DIR": str(workspace / 'inventory'),
        "ANSIBLE_CONFIG": str(runtime / 'ansible.cfg'),
        "SSL_CERT_FILE": str(ca_bundle),
        "ANSIBLE_COLLECTIONS_PATH": str(runtime / 'collections'),
        "ANSIBLE_ROLES_PATH": ':'.join(str(runtime / path) for path in (
            'range42/roles', 'range42-ansible_roles-proxmox_controller/roles',
            'range42-catalog/02_ansible_layer/admin/roles', 'range42-catalog/02_ansible_layer/trainee/roles')),
    }
    source = workspace / "sourced_range42.sh"
    # The API deliberately discovers only quoted literal exports, without sourcing them.
    def literal(value):
        quoted = shlex.quote(value)
        return quoted if quoted.startswith("'") else "'" + quoted + "'"
    private_write(source, "".join(f"export {name}={literal(value)}\n" for name, value in environment.items())
                  + 'export PATH=' + shlex.quote(str(state / 'venv/bin')) + ':"$PATH"\n')
    inventory = workspace / "inventory/inventory_default.yml"
    private_write(inventory, (scenario / 'hosts.yml').read_text())
    ssh_config = workspace / ("config_range42-" + workspace.name)
    if not ssh_config.exists():
        private_write(ssh_config, "Host *\n  StrictHostKeyChecking yes\n  UserKnownHostsFile "
                      + str(workspace / "ssh_keys/known_hosts") + "\n")
    if not (home / ".ssh/config").exists():
        private_write(home / ".ssh/config", "#### BEGIN RANGE42 INCLUDE\nInclude " + str(ssh_config)
                      + "\n#### END RANGE42 INCLUDE\n")
    if not (home / ".zshrc").exists():
        private_write(home / ".zshrc", "source " + shlex.quote(str(source)) + "\n")
    return workspace


def bootstrap_backend(plan, state, template, runtime):
    """Reuse CLI context initialization in API-owned state; public runtime stays read-only."""
    state, runtime = Path(state), Path(runtime)
    view = state / 'native-runtime'
    view.mkdir(parents=True, exist_ok=True, mode=0o700)
    playbooks = view / 'range42-playbooks'
    playbooks.mkdir(exist_ok=True, mode=0o700)
    for source in list(runtime.iterdir()) + [runtime / 'range42-playbooks/bundles']:
        if source.name == 'range42-playbooks':
            continue
        target = playbooks / 'bundles' if source.name == 'bundles' else view / source.name
        if target.is_symlink() and target.resolve() == source.resolve():
            continue
        if target.exists() or target.is_symlink():
            raise ValueError('Backend runtime view would replace unrelated state')
        target.symlink_to(source, target_is_directory=source.is_dir())
    workspace = bootstrap_cli(plan, state, template, view,
                              workspace_base=state / 'home/range42.config')
    home_runtime = state / 'home/range42'
    if home_runtime.exists() or home_runtime.is_symlink():
        if not home_runtime.is_symlink() or home_runtime.resolve() != view.resolve():
            raise ValueError('Backend CLI home points at unrelated runtime state')
    else:
        home_runtime.symlink_to(view, target_is_directory=True)
    keys = state / 'home/.ssh/range42' / workspace.name
    keys.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not keys.exists() and not keys.is_symlink() and (workspace / 'ssh_keys').exists():
        keys.symlink_to(workspace / 'ssh_keys', target_is_directory=True)
    return workspace


def seed_backend(plan, root):
    """Called on the backend VM, with its own token; never echo registration data."""
    root = Path(root)
    target = json.loads((root / "private/target.json").read_text())
    host = target["host"]
    if (not host["api_url"].startswith("https://") or host["node_name"] != plan["node"]
            or host.get("default_bridge") != plan["bridge"]):
        raise ValueError("Child Proxmox target does not match the platform plan")
    context = ssl.create_default_context(cafile=str(root / "runtime/proxmox-ca.pem"))
    permissions = request_json(host["api_url"].rstrip("/") + "/api2/json/access/permissions",
                               "PVEAPIToken=" + host["token_ref"], context=context)["data"]
    allowed = target["allowed_paths"]
    if any(p.startswith("/pool/") and p != f"/pool/r42-{plan['id']}" for p in allowed):
        raise ValueError("Child token pool must belong to this stack")
    validate_target_permissions(permissions, allowed)
    token = "Bearer " + (root / "private/api-token").read_text().strip()
    base = "http://" + node(plan, "backend")["ip"] + ":8000/v1"
    request_json(base + "/proxmox/hosts", token, host)
    existing = request_json(base + "/catalog/sources?limit=100", token)
    if existing["total"] > 100:
        raise ValueError("Installation has more than 100 sources; review registration explicitly")
    sources = target.get("sources")
    if sources is None:
        # Catalog sources currently require a branch/tag for shallow clones.
        # A runtime's exact commit is provenance, not a valid --branch argument.
        for kind in ("catalog", "bundles"):
            request_json(base + "/catalog/sources/default?kind=" + kind, token, {})
        sources = []
    for source in sources:
        if not any(item["provider"] == source["provider"]
                   and item["base_url"].rstrip("/") == source["base_url"].rstrip("/")
                   and [{k: r[k] for k in ("owner", "repo", "branch")} for r in item["repos"]] == source["repos"]
                   for item in existing["items"]):
            request_json(base + "/catalog/sources", token, source)
    ready = request_json(base + "/health/ready", token)
    if not ready.get("ready"):
        raise ValueError("Authenticated backend readiness did not pass")
    contexts = request_json(base + '/contexts', token)['items']
    label = json.loads((root / 'template/cli.json').read_text())['scenario']
    if not any(item['id'] == plan['id'] + '-' + label and item['ready'] for item in contexts):
        raise ValueError('The child backend native context is not ready')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("claim", "prepare", "validate-template", "seed", "bootstrap-cli", "bootstrap-backend"))
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--service")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.action == "validate-template":
        validate_template(args.root, plan["id"])
    elif args.action == "seed":
        seed_backend(plan, args.root)
    elif args.action == "bootstrap-cli":
        bootstrap_cli(plan, args.root / "state", args.root / "template", args.root / "runtime")
    elif args.action == "bootstrap-backend":
        bootstrap_backend(plan, args.root, Path('/run/range42-template'), Path('/runtime'))
    elif args.action == "claim":
        claim_node(plan, args.service, args.root)
    else:
        prepare_node(plan, args.service, args.root)


if __name__ == "__main__":
    main()
