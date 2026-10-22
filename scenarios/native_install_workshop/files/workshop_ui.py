#!/usr/bin/env python3
"""Prepare the participant's native UI/API on their own workshop CLI machine.

Public sources are pinned. Human credentials remain in the human context; the
backend receives a distinct API token, SSH key, vault and workspace.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import ssl
import stat
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request

PINS = {
    'range42': '178376b1280b9adf75e8414c2f743d3ec5bb7527',
    'range42-playbooks': 'cb32906e6b2453aed0f595383d92aa4831022ab4',
    'range42-catalog': '3de2f39bf7c94b7a68b508ed3be06c5dc0a81322',
    'range42-ansible_roles-proxmox_controller': 'e988001493041d6d2fd0c67b2006fe4e7686d374',
    'range42-ansible_roles-debug-devkit': 'bd0e8eafdd14dec9a8b3cca63248b5ddc14c9da3',
    'range42-backend-api': 'fc80911bc01272161a19d7cd10c0b3e6ea4988fa',
    'range42-deployer-ui': 'a6e97234269aba13c59d30782053591f2809aece',
}


def specification(marker, human, codename):
    username = marker.get('username', '')
    if (not re.fullmatch(r'user(?:0[1-9]|10)', username)
            or marker.get('role') != 'deployer'
            or not re.fullmatch(r'range42-workshop:[a-f0-9]{16,32}:' + re.escape(username) + r':deployer', marker.get('owner', ''))
            or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', codename)):
        raise ValueError('A valid participant CLI identity and codename are required')
    import ipaddress
    address = str(ipaddress.IPv4Address(marker['proxmox_address']))
    node = marker['proxmox_node']
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}', node):
        raise ValueError('A verified participant hypervisor identity is required')
    if (human.get('proxmox_api_host') != address + ':8006'
            or human.get('proxmox_node') != node
            or human.get('proxmox_dest_vm_storage_name') != 'local-lvm'):
        raise ValueError('This context does not target this participant hypervisor')
    return {'username': username, 'address': address, 'node': node, 'codename': codename,
            'context': codename + '-catalog_try', 'api_url': 'http://127.0.0.1:9013',
            'expires_at': marker['expires_at']}


def private_directory(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Private directories cannot be symbolic links')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('A private directory owned by the deployment user is required')
    return path


def private_write(path, content):
    path = Path(path)
    private_directory(path.parent)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('Refusing an unprotected or foreign private file')
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.workshop-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content.encode() if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def private_file_state(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError('Private retained installation state required')
    return path.read_text()


def export_repository(repo, destination, revision):
    repo, destination = Path(repo), Path(destination)
    if destination.exists() or destination.is_symlink() or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Runtime exports require an absent destination and exact commit')
    archive = subprocess.check_output(['git', '-C', str(repo), 'archive', revision])
    destination.mkdir(mode=0o755)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(destination, filter='data')
    (destination / '.range42-revision').write_text(revision + '\n')


def machine_vault(spec, service):
    context = spec['context']
    keys = f'/home/range42/.ssh/range42/{context}'
    code = spec['codename']
    vault = {
        'infrastructure_codename': code, 'infrastructure_scenario': 'catalog_try',
        'proxmox_address': spec['address'], 'proxmox_node': spec['node'],
        'proxmox_api_host': spec['address'] + ':8006', 'proxmox_api_user': service['user'],
        'proxmox_api_token_id': service['token_id'], 'proxmox_api_token_secret': service['token_secret'],
        'proxmox_dest_iso_storage_name': 'local', 'proxmox_dest_vm_storage_name': 'local-lvm',
        'proxmox_default_network_card_interface': 'vmbr0', 'proxmox_api_validate_certs': True,
        'range42_guest_hostkey_from_pve_agent': True, 'infrastructure_network_mode': 'sdn',
        'range42_sdn_zone': 'r42zone', 'range42_sdn_networks': [
            {'vnet': f'net{n}', 'subnet': f'192.168.{n}.0/24', 'gateway': f'192.168.{n}.1', 'snat': True}
            for n in range(140, 152)],
        'range42_fw_vm_ssh_sources': [], 'default_admin_vm_ci_user': 'alice',
        'default_admin_vm_ci_password': service['admin_password'],
        'default_admin_vm_ci_ssh_key': service['public_key'],
        'default_trainee_vm_ci_user': 'bob', 'default_trainee_vm_ci_password': service['admin_password'],
        'default_trainee_vm_ci_ssh_key': service['public_key'],
        'deployer_cli_user_ssh_known_hosts': f'/home/range42/range42.config/{context}/ssh_keys/known_hosts',
        'infrastructure_tailscale_authkey': '', 'infrastructure_tailscale_apikey': '',
        'ssh_key_px_root': f'{keys}/jump_keys/px.{context}-ssh_cli.root',
        'ssh_key_px_jump': f'{keys}/jump_keys/px.{context}-ssh_cli.jump_user',
        'ssh_key_deployer_admin': f'{keys}/backend_keys/r42.{context}-deployer-key_alice',
        'ssh_key_student_user': f'{keys}/student_keys/r42.{context}-student-key_bob',
    }
    for role in ('px_root', 'px_jump', 'deployer_admin', 'student_user'):
        vault['ssh_passphrase_' + role] = ''
        vault['ssh_key_' + role + '_pub_key'] = service['public_key']
    return vault


def run(*command, **kwargs):
    return subprocess.run(list(map(str, command)), check=True, **kwargs)


def clean_environment():
    return {k: v for k, v in os.environ.items() if not k.startswith(('ANSIBLE_', 'RANGE42_'))}


def prepare_sources(root):
    root.mkdir(parents=True, exist_ok=True)
    for name, revision in PINS.items():
        repo = root / name
        if not repo.exists():
            run('git', 'clone', '--branch', 'dev', 'https://github.com/range42/' + name + '.git', repo)
        if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain']).strip():
            raise ValueError('Preserve or commit local source changes before preparing workshop sources')
        run('git', '-C', repo, 'fetch', 'origin', revision)
        run('git', '-C', repo, 'checkout', '--detach', revision)


def api_call(spec, human, method, path, body=None):
    context = ssl.create_default_context(cafile='/etc/range42-workshop-pve-ca.pem')
    headers = {'Authorization': 'PVEAPIToken=' + human['proxmox_api_user'] + '!' +
               human['proxmox_api_token_id'] + '=' + human['proxmox_api_token_secret']}
    data = None if body is None else urllib.parse.urlencode(body).encode()
    request = urllib.request.Request('https://' + spec['address'] + ':8006/api2/json' + path,
                                     data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        return json.load(response)['data']


def service_credentials(spec, human, state_path):
    if state_path.exists():
        private_write(state_path, state_path.read_bytes())
        state = json.loads(state_path.read_text())
        if state['spec'] != spec:
            raise ValueError('The retained UI installation belongs to a different context')
        return state['service']
    from datetime import datetime
    user = 'r42-workshop-ui@pve'
    users = api_call(spec, human, 'GET', '/access/users')
    if any(x['userid'] == user for x in users):
        raise ValueError('An existing automation identity has no retained local credentials; refusing adoption')
    service = {'user': user, 'token_id': 'ui', 'admin_password': secrets.token_urlsafe(24)}
    api_call(spec, human, 'POST', '/access/users', {'userid': user, 'comment': 'Range42 workshop ' + spec['username']})
    api_call(spec, human, 'PUT', '/access/acl', {'path': '/', 'users': user, 'roles': 'Administrator'})
    token = api_call(spec, human, 'POST', '/access/users/' + user + '/token/ui',
                     {'privsep': 0, 'expire': int(datetime.fromisoformat(spec['expires_at']).timestamp())})
    service['token_secret'] = token['value']
    key_path = state_path.parent / 'service-ed25519'
    run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'range42-workshop-ui-' + spec['username'], '-f', key_path)
    service['private_key'] = key_path.read_text()
    service['public_key'] = key_path.with_suffix('.pub').read_text().strip()
    # Retain immediately; retries use this one identity instead of rotating it.
    private_write(state_path, json.dumps({'spec': spec, 'service': service}))
    return service


def proxmox_ssh(spec, human):
    import paramiko
    key_type, key_data, *_ = Path('/etc/range42-workshop-pve-hostkey.pub').read_text().split()
    key = paramiko.Ed25519Key(data=base64.b64decode(key_data))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.get_host_keys().add(spec['address'], key_type, key)
    client.connect(spec['address'], username='root', key_filename=human['ssh_key_px_root'],
                   passphrase=human['ssh_passphrase_px_root'], look_for_keys=False, allow_agent=False)
    return client


def authorize_service_key(spec, human, service):
    client = proxmox_ssh(spec, human)
    try:
        # Only append this machine's public key; existing human keys are preserved.
        script = '''import pathlib,pwd,os,sys
key=sys.stdin.read().strip()
assert key.startswith('ssh-ed25519 ') and '\\n' not in key
for username in ['root','jump_user']:
 u=pwd.getpwnam(username);d=pathlib.Path(u.pw_dir)/'.ssh';d.mkdir(mode=0o700,exist_ok=True)
 p=d/'authorized_keys'
 if p.is_symlink():
  assert username=='root' and str(p.resolve())=='/etc/pve/priv/authorized_keys' and p.stat().st_uid==0
  p=p.resolve()
 old=p.read_text() if p.exists() else ''
 if key not in old.splitlines():
  with p.open('a') as f:f.write(('\\n' if old and not old.endswith('\\n') else '')+key+'\\n')
 if username!='root':
  p.chmod(0o600);os.chown(d,u.pw_uid,u.pw_gid);os.chown(p,u.pw_uid,u.pw_gid)
'''
        stdin, stdout, stderr = client.exec_command('python3 -c ' + shlex.quote(script))
        stdin.write(service['public_key'])
        stdin.channel.shutdown_write()
        if stdout.channel.recv_exit_status():
            raise ValueError('Could not authorize the separate UI automation key')
    finally:
        client.close()


def template_agent_plan(template, storage):
    if (template.get('name') != 'template-vm-small-01-4g-32g' or template.get('template') != 1
            or storage.get('type') != 'dir' or storage.get('path') != '/var/lib/vz'):
        raise ValueError('Build the workshop catalog_try template before installing its UI')
    filename = 'range42-workshop-agent-9221.yml'
    vendor_ref = 'vendor=local:snippets/' + filename
    custom = [item for item in template.get('cicustom', '').split(',') if item]
    if any(item.startswith('vendor=') and item != vendor_ref for item in custom):
        raise ValueError('Preserve the existing template vendor configuration before UI setup')
    if vendor_ref not in custom:
        custom.append(vendor_ref)
    content = set(filter(None, storage.get('content', '').split(','))) | {'snippets'}
    return {'filename': filename, 'storage_content': ','.join(sorted(content)),
            'config': {'agent': 'enabled=1', 'cicustom': ','.join(custom)},
            'vendor': '#cloud-config\n# range42-workshop: guest identity verification\n'
                      'package_update: true\npackages:\n  - qemu-guest-agent\n'
                      'runcmd:\n  - [systemctl, enable, --now, qemu-guest-agent]\n'}


def prepare_guest_agent_template(spec, human):
    # Only this participant's native 9221 template is prepared. New clones inherit
    # the agent channel and install its service through cloud-init before trust
    # enrollment, without accepting a key from an unauthenticated SSH scan.
    import inspect
    script = 'import pathlib,json,subprocess,socket,sys,os,stat,tempfile\n' + inspect.getsource(template_agent_plan) + '''
x=json.load(sys.stdin)
assert socket.gethostname().split('.')[0] == x['node']
def read(path):
 return json.loads(subprocess.check_output(['pvesh','get',path,'--output-format','json'],text=True))
path='/nodes/'+x['node']+'/qemu/9221/config'
template=read(path);storage=read('/storage/local');plan=template_agent_plan(template,storage)
directory=pathlib.Path('/var/lib/vz/snippets')
assert not directory.is_symlink()
directory.mkdir(mode=0o755,exist_ok=True)
assert directory.stat().st_uid==0 and not directory.stat().st_mode & 0o022
target=directory/plan['filename']
if target.exists() or target.is_symlink():
 info=target.lstat()
 assert stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode & 0o022
 assert target.read_text()==plan['vendor']
else:
 fd,temporary=tempfile.mkstemp(dir=directory,prefix='.range42-agent-')
 with os.fdopen(fd,'w') as output:output.write(plan['vendor']);output.flush();os.fsync(output.fileno())
 os.chmod(temporary,0o644);os.replace(temporary,target)
if storage.get('content')!=plan['storage_content']:
 subprocess.run(['pvesh','set','/storage/local','--content',plan['storage_content']],check=True,stdout=subprocess.DEVNULL)
args=['pvesh','set',path,'--agent',plan['config']['agent'],'--cicustom',plan['config']['cicustom']]
if template.get('digest'):args+=['--digest',template['digest']]
subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
result=read(path)
assert 'enabled=1' in result['agent'] and result['cicustom']==plan['config']['cicustom']
print(json.dumps({'template':9221,'guest_agent_bootstrap_ready':True}))
'''
    client = proxmox_ssh(spec, human)
    try:
        stdin, stdout, stderr = client.exec_command('python3 -c ' + shlex.quote(script), timeout=60)
        stdin.write(json.dumps({'node': spec['node']}))
        stdin.channel.shutdown_write()
        output = stdout.read()
        if stdout.channel.recv_exit_status() or json.loads(output).get('guest_agent_bootstrap_ready') is not True:
            raise ValueError('Guest agent template preparation stopped; existing credentials were preserved')
    finally:
        client.close()


def owned_system_directory(path):
    path = Path(path)
    if not path.exists():
        run('sudo', '-n', 'install', '-d', '-m', '0700', '-o', str(os.getuid()), '-g', str(os.getgid()), path)
    return private_directory(path)


def render(template, values):
    from jinja2 import Environment, StrictUndefined
    environment = Environment(undefined=StrictUndefined)
    environment.filters['mandatory'] = lambda x: x
    environment.globals['lookup'] = lambda plugin, name: '/runtime/range42-playbooks/bundles' if (plugin, name) == ('env', 'RANGE42_BUNDLE_DIR') else ''
    return environment.from_string(template.read_text()).render(**values)


def runtime_ansible_config():
    # Preserve verified host keys while detecting dead SSH sessions during boot.
    return ('[defaults]\nhost_key_checking = True\ninterpreter_python = auto_silent\n'
            'retry_files_enabled = False\n[ssh_connection]\n'
            'ssh_args = -C -o ControlMaster=auto -o ControlPersist=60s '
            '-o ServerAliveInterval=15 -o ServerAliveCountMax=3\nretries = 3\n')


def prepare_runtime_and_context(root, context, spec, service, human):
    import yaml
    runtime = owned_system_directory('/opt/range42/runtime')
    for name, revision in PINS.items():
        if name in ('range42-backend-api', 'range42-deployer-ui'):
            continue
        destination = runtime / name
        if not destination.exists():
            export_repository(root / name, destination, revision)
        elif (destination / '.range42-revision').read_text().strip() != revision:
            raise ValueError('Existing runtime revision differs; use the maintenance workflow')
    collections = runtime / 'collections'
    if not (collections / 'ansible_collections').exists():
        collections.mkdir(exist_ok=True)
        candidates = [Path('/usr/share/ansible/collections/ansible_collections'), Path('/usr/lib/python3/dist-packages/ansible_collections')]
        source = next((p for p in candidates if p.is_dir()), None)
        if source is None:
            raise ValueError('Install the native Ansible collections before UI setup')
        shutil.copytree(source, collections / 'ansible_collections', symlinks=False)
    config = runtime_ansible_config()
    (runtime / 'ansible.cfg').write_text(config)
    (runtime / 'proxmox-ca.pem').write_text(Path('/etc/ssl/certs/ca-certificates.crt').read_text() + '\n' + Path('/etc/range42-workshop-pve-ca.pem').read_text())
    home = owned_system_directory('/var/lib/range42/backend-home')
    workspaces = owned_system_directory('/var/lib/range42/backend-workspaces')
    template = owned_system_directory('/var/lib/range42/private/workspace-template')
    secrets_dir = owned_system_directory('/var/lib/range42/private/api-secrets')
    owned_system_directory('/var/lib/range42/backend')
    for name, value in [('api-token', secrets.token_urlsafe(48)), ('credential-key', base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())]:
        if not (secrets_dir / name).exists():
            private_write(secrets_dir / name, value + '\n')
    workspace = private_directory(workspaces / spec['context'])
    for base in (workspace, template):
        private_directory(base / 'secrets')
        private_directory(base / 'ssh_keys')
        if not (base / 'secrets/vault_pass.txt').exists():
            private_write(base / 'secrets/vault_pass.txt', secrets.token_urlsafe(48) + '\n')
            encrypted = subprocess.check_output(['ansible-vault', 'encrypt', '--vault-password-file', str(base / 'secrets/vault_pass.txt'), '--output', '-'],
                input=yaml.safe_dump(machine_vault(spec, service)).encode(), env=clean_environment())
            private_write(base / 'secrets/default_vault.yml', encrypted)
        public = Path('/etc/range42-workshop-pve-hostkey.pub').read_text().split()
        private_write(base / 'ssh_keys/known_hosts', spec['address'] + ' ' + ' '.join(public[:2]) + '\n')
        vault = machine_vault(spec, service)
        for field in ('ssh_key_px_root', 'ssh_key_px_jump', 'ssh_key_deployer_admin', 'ssh_key_student_user'):
            location = Path(vault[field]).relative_to('/home/range42/.ssh/range42/' + spec['context'])
            private_directory(base / 'ssh_keys' / location.parent)
            private_write(base / 'ssh_keys' / location, service['private_key'])
    ssh_home = private_directory(home / '.ssh')
    key_home = private_directory(ssh_home / 'range42' / spec['context'])
    for directory in ('backend_keys', 'jump_keys', 'student_keys'):
        private_directory(key_home / directory)
        for key in (workspace / 'ssh_keys' / directory).iterdir():
            private_write(key_home / directory / key.name, key.read_bytes())
    private_directory(workspace / 'inventory')
    private_write(workspace / 'inventory/inventory_default.yml', (context / 'inventory/inventory_default.yml').read_bytes())
    values = {'INFRASTRUCTURE_CODENAME': spec['codename'], 'INFRASTRUCTURE_SCENARIO': 'catalog_try',
              'INFRASTRUCTURE_PROXMOX_ADDRESS': spec['address'], 'DEPLOYER_CLI__DST_GIT_DIR': '/runtime',
              'DEPLOYER_CLI__DST_CONFIG_BASE_DIR': '/home/range42/range42.config',
              'DEPLOYER_CLI__DST_SSH_KEYS_JUMP_DEST_DIR': f'/home/range42/.ssh/range42/{spec["context"]}/jump_keys',
              'DEPLOYER_CLI__DST_SSH_KEYS_BACKEND_DEST_DIR': f'/home/range42/.ssh/range42/{spec["context"]}/backend_keys'}
    private_write(workspace / 'sourced_range42.sh', render(runtime / 'range42/roles/workspace.credentials/templates/sourced_range42.j2', values))
    config_text = render(runtime / 'range42-playbooks/scenarios/catalog_try/templates/ssh-config.j2', values)
    private_write(ssh_home / 'config', config_text + '\nHost *\n    StrictHostKeyChecking yes\n    UserKnownHostsFile /home/range42/range42.config/' + spec['context'] + '/ssh_keys/known_hosts\n')
    private_write(home / '.zshrc', 'source /runtime/range42/roles/deployer.bootstrap/files/range42-context.sh\nsource /home/range42/range42.config/' + spec['context'] + '/sourced_range42.sh\n')
    return runtime


def native_bundle(root, context, spec, name):
    import yaml
    settings = {
        'global_vm_ssh_name': 'workshop-local', 'global_vm_ci_ip': '127.0.0.1',
        'UI_PORT': 3000, 'BACKEND_API_URL': spec['api_url'], 'PROXMOX_NODE_NAME': spec['node'],
        'INSTALL_TAILSCALE': 'NO', 'API_PORT': 9013, 'BACKEND_LISTEN_ADDRESS': '127.0.0.1',
        'BACKEND_CORS_ORIGINS': 'http://127.0.0.1:3000,http://localhost:3000',
        'API_SECRETS_DIR_HOST': '/var/lib/range42/private/api-secrets',
        'RUNTIME_DIR_HOST': '/opt/range42/runtime', 'WORKSPACE_TEMPLATE_DIR_HOST': '/var/lib/range42/private/workspace-template',
        'WORKSPACE_DIR_HOST': '/var/lib/range42/backend-workspaces', 'API_CONTAINER_IMAGE': 'range42-backend-api:workshop',
    }
    if name.endswith('backend'):
        settings['LOCAL_CODE_PATH'] = str(api_build_context(root)) + '/'
    directory = private_directory(Path.home() / '.local/state/range42-workshop')
    private_write(directory / 'local-inventory.yml', yaml.safe_dump({'all': {'hosts': {'workshop-local': {
        'ansible_connection': 'local', 'ansible_python_interpreter': '/usr/bin/python3'}}}}))
    private_write(directory / 'ui-vars.yml', yaml.safe_dump(settings))
    environment = clean_environment()
    environment.update(RANGE42_GITDIR__ROOT_DIR=str(root), RANGE42_ACTIVE_CONFIG_DIR=str(context),
                       RANGE42_ACTIVE_WORKSPACE=spec['context'], RANGE42_INFRASTRUCTURE_CODENAME=spec['codename'],
                       RANGE42_BUNDLE_DIR=str(root / 'range42-playbooks/bundles'),
                       ANSIBLE_ROLES_PATH=':'.join(str(root / p) for p in [
                           'range42/roles', 'range42-catalog/02_ansible_layer/admin/roles',
                           'range42-catalog/02_ansible_layer/trainee/roles', 'range42-ansible_roles-proxmox_controller/roles']))
    # The API's registration must use the dedicated machine vault, not the human vault.
    active = Path('/var/lib/range42/backend-workspaces') / spec['context'] if name.endswith('backend') else context
    environment['RANGE42_ACTIVE_CONFIG_DIR'] = str(active)
    run('ansible-playbook', root / f'range42-playbooks/bundles/admin/software.install.deployer_{name}/main.yml',
        '-i', directory / 'local-inventory.yml', '-e', '@' + str(directory / 'ui-vars.yml'),
        '--vault-password-file', active / 'secrets/vault_pass.txt', env=environment)


def api_build_context(root):
    # The installer keeps its user checkout private. Export reviewed public
    # files with Git's modes so the image's non-root API can import them.
    builds = owned_system_directory('/opt/range42/builds')
    revision = PINS['range42-backend-api']
    destination = builds / ('api-' + revision[:12] + '-' + secrets.token_hex(6))
    export_repository(root / 'range42-backend-api', destination, revision)
    # Python's data extraction filter leaves directory modes to the private
    # installer umask. Normalize only this credential-free Git export.
    for public in [destination, *destination.rglob('*')]:
        if not public.is_symlink():
            public.chmod(0o755 if public.is_dir() or public.stat().st_mode & 0o111 else 0o644)
    return destination


def runtime_manifest(root, runtime):
    image = 'range42-backend-api:workshop'
    run('sudo', '-n', 'docker', 'build', '-t', image, api_build_context(root))
    environment = {'RANGE42_BUNDLE_DIR': '/runtime/range42-playbooks/bundles',
                   'RANGE42_GITDIR__ROOT_DIR': '/runtime',
                   'RANGE42_INVENTORY__DOCKER__CTF': '/runtime/range42-catalog/03_container_layer/docker/_ctf',
                   'ANSIBLE_CONFIG': '/runtime/ansible.cfg', 'ANSIBLE_COLLECTIONS_PATH': '/runtime/collections',
                   'ANSIBLE_ROLES_PATH': '/runtime/range42-ansible_roles-proxmox_controller/roles:/runtime/range42-catalog/02_ansible_layer/admin/roles:/runtime/range42-catalog/02_ansible_layer/trainee/roles:/runtime/range42/roles'}
    components = {name: '/runtime/' + name for name in PINS if name not in ('range42-backend-api', 'range42-deployer-ui')}
    components.update(collections='/runtime/collections', ansible_config='/runtime/ansible.cfg', ca='/runtime/proxmox-ca.pem')
    script = 'import json;from pathlib import Path;from app.core.bundle_runtime import build_runtime_manifest;print(json.dumps(build_runtime_manifest({k:Path(v) for k,v in json.loads(' + repr(json.dumps(components)) + ').items()})))'
    command = ['sudo', '-n', 'docker', 'run', '--rm', '--network', 'none', '--read-only', '-v', str(runtime) + ':/runtime:ro']
    for key, value in environment.items():
        command += ['-e', key + '=' + value]
    result = subprocess.check_output(command + ['--entrypoint', 'python', image, '-c', script])
    json.loads(result)
    (runtime / 'bundle-runtime.json').write_bytes(result)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install', 'ui'])
    parser.add_argument('codename', nargs='?')
    args = parser.parse_args()
    root = Path.home() / 'range42'
    if args.action == 'prepare':
        import yaml
        prepare_sources(root)
        release = root / 'workshop-revisions.yml'
        release.write_text(yaml.safe_dump(PINS))
        release.chmod(0o644)
        print('Workshop source revisions prepared. Run: range42-workshop install')
        return
    import yaml
    if args.action == 'install':
        release = root / 'workshop-revisions.yml'
        if yaml.safe_load(release.read_text()) != PINS:
            raise ValueError('Run range42-workshop prepare before the native installer')
        environment = clean_environment()
        environment['RANGE42_REPOSITORY_REVISIONS_FILE'] = str(release)
        run('/usr/bin/python3', root / 'range42/range42-init.py', '--catalog-try', 'docker/_ctf/hello', env=environment)
        return
    marker_path = Path('/etc/range42-workshop.json')
    info = marker_path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('A facilitator-owned instance identity is required')
    marker = json.loads(marker_path.read_text())
    if not args.codename or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', args.codename):
        raise ValueError('Supply the codename used for your catalog_try CLI installation')
    context = Path.home() / 'range42.config' / (args.codename + '-catalog_try')
    human = yaml.safe_load(subprocess.check_output(['ansible-vault', 'view', '--vault-password-file',
        str(context / 'secrets/vault_pass.txt'), str(context / 'secrets/default_vault.yml')], env=clean_environment()))
    spec = specification(marker, human, args.codename)
    directory = private_directory(Path.home() / '.local/state/range42-workshop')
    state = directory / 'ui.json'
    print('WORKSHOP_STAGE service_credentials', flush=True)
    try:
        with urllib.request.urlopen(spec['api_url'] + '/v1/health', timeout=2) as response:
            running = response.status == 200
    except (OSError, urllib.error.URLError):
        running = False
    if running:
        if not state.exists() or json.loads(private_file_state(state))['spec'] != spec:
            raise ValueError('A running API has no matching retained installation identity')
        token = Path('/var/lib/range42/private/api-secrets/api-token').read_text().strip()
        request = urllib.request.Request(spec['api_url'] + '/v1/health/ready', headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(request, timeout=15) as response:
            if json.load(response).get('ready') is not True:
                raise ValueError('Existing API is not ready; inspect it before maintenance')
        print('Existing workshop API is ready. Its service and credentials were preserved.')
        return
    service = service_credentials(spec, human, state)
    print('WORKSHOP_STAGE authorize_service_key', flush=True)
    authorize_service_key(spec, human, service)
    print('WORKSHOP_STAGE prepare_guest_agent_template', flush=True)
    prepare_guest_agent_template(spec, human)
    native_bundle(root, context, spec, 'ui')
    runtime = prepare_runtime_and_context(root, context, spec, service, human)
    runtime_manifest(root, runtime)
    native_bundle(root, context, spec, 'api_backend')
    print('UI ready at http://127.0.0.1:3000 through your SSH tunnel.')
    print('Backend bearer token: /var/lib/range42/private/api-secrets/api-token (keep private).')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as error:
        import traceback
        print("Failure type:", type(error).__name__, "status:", getattr(error, "code", None))
        print("Failure location:", [(Path(f.filename).name, f.lineno, f.name) for f in traceback.extract_tb(error.__traceback__)][-5:])
        raise SystemExit('Workshop UI setup stopped. Retained credentials are preserved; inspect the private installation log.') from None
