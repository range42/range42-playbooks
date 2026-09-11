"""Validate a managed installation and render its explicit Compose contract."""
from __future__ import annotations

import ipaddress
from pathlib import Path
import re
from urllib.parse import urlsplit

_FIELDS = {'root', 'name', 'image', 'uid', 'gid', 'state_dir', 'workspace_host',
           'workspace_container', 'database_container', 'secrets_dir', 'port',
           'listen_address', 'cors_origins', 'git_allowed_hosts', 'runtime_dir',
           'workspace_template_dir'}
STATE_CONTAINER = Path('/var/lib/range42')


def host_path(value: str) -> str:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError('Host bindings must be absolute paths')
    path = Path(value)
    if path != path.resolve():
        raise ValueError('Host bindings cannot contain symbolic links or unresolved path segments')
    return str(path)


def validate_config(raw: dict) -> dict:
    if not isinstance(raw, dict) or set(raw) - _FIELDS:
        raise ValueError('Unknown installer configuration fields')
    for key in ('root', 'name', 'image', 'uid', 'gid'):
        if key not in raw:
            raise ValueError('Missing required installer configuration')
    root = host_path(raw['root'])
    if not isinstance(raw['name'], str) or not re.fullmatch('[a-z][a-z0-9-]{0,31}', raw['name']):
        raise ValueError('Installation name must be a short lowercase identifier')
    if not isinstance(raw['image'], str) or not re.fullmatch(r'(?:sha256:|[a-zA-Z0-9./:_-]+@sha256:)[0-9a-f]{64}', raw['image']):
        raise ValueError('Use an immutable image ID or repository digest')
    for key in ('uid', 'gid'):
        if type(raw[key]) is not int or not 0 <= raw[key] < 2**31:
            raise ValueError('Image UID and GID must be explicit integers')
    port = raw.get('port', 8000)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Listener port must be between 1 and 65535')
    address = str(ipaddress.ip_address(raw.get('listen_address', '127.0.0.1')))
    state = host_path(raw.get('state_dir', root + '/state'))
    workspace = host_path(raw.get('workspace_host', state + '/workspaces'))
    secrets_dir = host_path(raw.get('secrets_dir', root + '/secrets'))
    for writable in (Path(state), Path(workspace)):
        if (Path(root).is_relative_to(writable)
                or Path(secrets_dir).is_relative_to(writable)
                or writable.is_relative_to(secrets_dir)):
            raise ValueError('Writable mounts cannot overlap installer records or credentials')
    inside = Path(raw.get('workspace_container', '/var/lib/range42/workspaces'))
    if not inside.is_absolute() or '..' in inside.parts or not (
            inside.is_relative_to(STATE_CONTAINER / 'workspaces') or inside.is_relative_to('/home')):
        raise ValueError('Workspace container binding must use persistent workspace or legacy home paths')
    database = Path(raw.get('database_container', str(inside / '.range42.db')))
    if not database.is_relative_to(inside) or database == inside or '..' in database.parts:
        raise ValueError('Database must remain inside the explicitly mapped workspace')
    origins = raw.get('cors_origins', [])
    if not isinstance(origins, list):
        raise ValueError('CORS origins must be an explicit list')
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('CORS requires exact HTTP origins without paths')
    forges = raw.get('git_allowed_hosts', ['github.com', 'gitlab.com', 'codeberg.org'])
    if (not isinstance(forges, list) or not forges
            or any(not isinstance(host, str) or not re.fullmatch('[a-zA-Z0-9.-]+(?::[0-9]+)?', host) for host in forges)):
        raise ValueError('Git hosts must be explicit DNS names with optional ports')
    runtime = host_path(raw['runtime_dir']) if raw.get('runtime_dir') else None
    template = host_path(raw['workspace_template_dir']) if raw.get('workspace_template_dir') else None
    if bool(runtime) != bool(template):
        raise ValueError('Execution runtime and private workspace template must be configured together')
    return {'root': root, 'name': raw['name'], 'image': raw['image'], 'uid': raw['uid'], 'gid': raw['gid'],
            'state_dir': state, 'workspace_host': workspace, 'workspace_container': str(inside),
            'database_container': str(database), 'database_host': str(Path(workspace) / database.relative_to(inside)),
            'secrets_dir': secrets_dir, 'port': port,
            'listen_address': address, 'cors_origins': origins, 'git_allowed_hosts': forges,
            'runtime_dir': runtime, 'workspace_template_dir': template}


def compose_document(plan: dict, release: str) -> dict:
    def bind(source, target, readonly=False):
        return {'type': 'bind', 'source': source, 'target': target, 'read_only': readonly,
                'bind': {'create_host_path': False}}

    environment = {'HOME': '/var/lib/range42/home', 'RANGE42_AUTH_MODE': 'required',
                   'RANGE42_WORKSPACE_ROOT': plan['workspace_container'],
                   'RANGE42_DB_URL': 'sqlite+aiosqlite:///' + plan['database_container'],
                   'RANGE42_API_TOKEN_FILE': '/run/secrets/api_token',
                   'RANGE42_CREDENTIAL_KEY_FILE': '/run/secrets/credential_key',
                   'RANGE42_MAINTENANCE_LOCK_FILE': '/var/lib/range42/maintenance.lock',
                   'RANGE42_CORS_ORIGINS': ','.join(plan['cors_origins']),
                   'RANGE42_GIT_ALLOWED_HOSTS': ','.join(plan['git_allowed_hosts'])}
    mounts = [bind(plan['state_dir'], str(STATE_CONTAINER)),
              bind(plan['workspace_host'], plan['workspace_container']),
              bind(plan['secrets_dir'] + '/api-token', '/run/secrets/api_token', True),
              bind(plan['secrets_dir'] + '/credential-key', '/run/secrets/credential_key', True)]
    if plan['runtime_dir']:
        mounts += [bind(plan['runtime_dir'], '/runtime', True),
                   bind(plan['workspace_template_dir'], '/run/range42-template', True)]
        environment.update({
            'API_BACKEND_PUBLIC_PLAYBOOKS_DIR': '/runtime/range42-playbooks',
            'API_BACKEND_WWWAPP_PLAYBOOKS_DIR': '/runtime/range42-playbooks',
            'RANGE42_BUNDLE_DIR': '/runtime/range42-playbooks/bundles',
            'RANGE42_BUNDLE_RUNTIME_MANIFEST': '/runtime/bundle-runtime.json',
            'RANGE42_WORKSPACE_TEMPLATE_DIR': '/run/range42-template',
            'RANGE42_PROXMOX_CA_FILE': '/runtime/proxmox-ca.pem',
            'RANGE42_INVENTORY__DOCKER__CTF': '/runtime/range42-catalog/03_container_layer/docker/_ctf',
            'ANSIBLE_CONFIG': '/runtime/ansible.cfg', 'ANSIBLE_COLLECTIONS_PATH': '/runtime/collections',
            'ANSIBLE_ROLES_PATH': '/runtime/range42-ansible_roles-proxmox_controller/roles:'
                                  '/runtime/range42-catalog/02_ansible_layer/admin/roles:'
                                  '/runtime/range42-catalog/02_ansible_layer/trainee/roles:/runtime/range42/roles'})
    return {'services': {'api': {'image': plan['image'], 'pull_policy': 'never', 'init': True,
            'container_name': plan['name'] + '-' + release[:16],
            'labels': {'org.range42.installation': plan['root'], 'org.range42.release': release},
            'user': f"{plan['uid']}:{plan['gid']}", 'environment': environment, 'volumes': mounts,
            'ports': [{'target': 8000, 'published': str(plan['port']), 'host_ip': plan['listen_address'], 'protocol': 'tcp'}],
            'read_only': True, 'tmpfs': ['/tmp:mode=1777,size=256m'],
            'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
            'stop_grace_period': '60s', 'restart': 'unless-stopped'}}}
