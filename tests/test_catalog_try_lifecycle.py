"""Execute native Delete/Reset wrappers with PVE recorders and real SSH trust."""
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUEST = {'vm_id': 1250, 'vm_name': 'catalog-try-vm-docker', 'proxmox_node': 'owned-node', 'template': 0}
TEMPLATE = {'vm_id': 9221, 'vm_name': 'template-vm-small-01-4g-32g', 'template': 1}


def fixture(tmp_path, *, initial=None, after=None, managed=True, alias=None, port=22):
    scenario = tmp_path / 'scenario'
    shutil.copytree(ROOT / 'scenarios/catalog_try', scenario)
    home, context, binary = [tmp_path / name for name in ('home', 'context', 'bin')]
    for parent in (home / '.ssh', context / 'ssh_keys', binary):
        parent.mkdir(parents=True, mode=0o700)
    key = tmp_path / 'fixture-key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    public = ' '.join(key.with_suffix('.pub').read_text().split()[:2])
    ip = '192.168.142.250'
    target = alias if alias is not None else ip if port == 22 else f'[{ip}]:{port}'
    ssh_config = tmp_path / 'ssh config'
    ssh_config.write_text('Host r42.catalog-try-vm-docker\n HostName ' + ip + '\n Port ' + str(port)
        + ('\n HostKeyAlias ' + alias if alias is not None else '') + '\n GlobalKnownHostsFile /dev/null\n')
    pins = (context / 'ssh_keys' if managed else home / '.ssh') / 'known_hosts'
    pins.write_text('10.77.32.18 ' + public + '\n' + target + ' ' + public + '\n192.0.2.77 ' + public + '\n')
    pins.chmod(0o600)
    if managed:
        (home / '.ssh/known_hosts').write_text('foreign-context.example ' + public + '\n')
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'listings': [
        {'rows': [GUEST, TEMPLATE] if initial is None else initial},
        {'rows': [TEMPLATE] if after is None else after}]}))
    calls = tmp_path / 'calls.jsonl'
    state = tmp_path / 'state.json'
    state.write_text('{"queries":0}')
    code = f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
p=json.loads(Path(os.environ['TEST_PLAN']).read_text());s=Path(os.environ['TEST_STATE']);state=json.loads(s.read_text())
name=Path(sys.argv[0]).name
body=sys.stdin.read() if name!='proxmox_vm.list.to.jsons.sh' else ''
with open(os.environ['TEST_CALLS'],'a') as f:f.write(json.dumps({{'name':name,'stdin':body,'argv':sys.argv[1:]}})+'\\n')
if name=='proxmox_vm.list.to.jsons.sh':
 i=state['queries'];state['queries']+=1;s.write_text(json.dumps(state));item=p['listings'][min(i,len(p['listings'])-1)]
 if i and p.get('race'):
  with open(os.environ['TEST_PINS'],'a') as f:f.write(p['race'])
 if 'raw' in item:print(item['raw'])
 else:
  for r in item['rows']:print(json.dumps(r,separators=(',',':')))
 sys.exit(item.get('code',0))
sys.exit(p.get('failures',{{}}).get(name,0))
'''
    for name in ('proxmox_vm.list.to.jsons.sh', 'proxmox_vm.vm_id.stop_force.to.jsons.sh',
                 'proxmox_vm.vm_id.delete.to.jsons.sh', 'ansible-playbook'):
        path = binary / name
        path.write_text(code)
        path.chmod(0o700)
    env = {**os.environ, 'HOME': str(home), 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
        'RANGE42_SOURCE_CONTEXT_DIR': str(context) if managed else '',
        'ANSIBLE_SSH_COMMON_ARGS': '-F ' + shlex.quote(str(ssh_config)), 'ANSIBLE_SSH_EXTRA_ARGS': '',
        'RANGE42_ANSIBLE_ROLES__INVENTORY_DIR': '/fixture/inventory', 'RANGE42_VAULT_PASSWORD_FILE': '/fixture/vault',
        'TEST_PLAN': str(plan), 'TEST_STATE': str(state), 'TEST_CALLS': str(calls), 'TEST_PINS': str(pins)}
    return {'scenario': scenario, 'pins': pins, 'home': home, 'plan': plan, 'calls': calls,
            'env': env, 'public': public, 'target': target, 'config': ssh_config}


def run(f, entry='delete_vms_only', args=()):
    result = subprocess.run(['bash', str(f['scenario'] / f'catalog_try.{entry}.sh'), *args],
        cwd=f['scenario'], env=f['env'], capture_output=True, text=True, timeout=20, check=False)
    calls = [json.loads(line) for line in f['calls'].read_text().splitlines()] if f['calls'].exists() else []
    return result, calls


def update(f, **values):
    plan = json.loads(f['plan'].read_text())
    plan.update(values)
    f['plan'].write_text(json.dumps(plan))


@pytest.mark.parametrize('entry', ['delete_vms_only', 'reset.setup'])
@pytest.mark.parametrize('managed', [True, False])
@pytest.mark.parametrize('binding', [(None, 22), (None, 2222), ('owned-guest-alias', 22)])
def test_only_selected_guest_pin_retires_after_independent_absence(tmp_path, entry, managed, binding):
    f = fixture(tmp_path, managed=managed, alias=binding[0], port=binding[1])
    home_before = (f['home'] / '.ssh/known_hosts').read_bytes()
    result, calls = run(f, entry, ('--start-at-task', 'fixed task; no interpretation'))
    assert result.returncode == 0, result.stdout + result.stderr
    assert [c['name'] for c in calls] == ['proxmox_vm.list.to.jsons.sh',
        'proxmox_vm.vm_id.stop_force.to.jsons.sh', 'proxmox_vm.vm_id.delete.to.jsons.sh',
        'proxmox_vm.list.to.jsons.sh'] + (['ansible-playbook'] if entry == 'reset.setup' else [])
    for c in calls[1:3]:
        assert [json.loads(line) for line in c['stdin'].splitlines()] == [GUEST]
    assert f['pins'].read_text() == '10.77.32.18 ' + f['public'] + '\n192.0.2.77 ' + f['public'] + '\n'
    if managed:
        assert (f['home'] / '.ssh/known_hosts').read_bytes() == home_before
    if entry == 'reset.setup':
        assert calls[-1]['argv'][-2:] == ['--start-at-task', 'fixed task; no interpretation']


@pytest.mark.parametrize('initial', [[], [TEMPLATE]])
def test_verified_already_absent_recovery_also_retires_stale_pin(tmp_path, initial):
    f = fixture(tmp_path, initial=initial)
    result, calls = run(f)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [c['name'] for c in calls] == ['proxmox_vm.list.to.jsons.sh'] * 2
    assert f['target'] not in f['pins'].read_text()
    assert '10.77.32.18' in f['pins'].read_text()


@pytest.mark.parametrize('fault', ['initial_error', 'initial_malformed', 'duplicate_id', 'wrong_name', 'template',
    'stop_error', 'delete_error', 'post_error', 'post_malformed', 'post_present', 'ssh_destination', 'pin_race'])
@pytest.mark.parametrize('entry', ['delete_vms_only', 'reset.setup'])
def test_failures_preserve_pins_and_never_start_reset_install(tmp_path, fault, entry):
    f = fixture(tmp_path)
    before = f['pins'].read_bytes()
    data = json.loads(f['plan'].read_text())
    if fault == 'initial_error':
        data['listings'][0]['code'] = 19
    elif fault == 'initial_malformed':
        data['listings'][0] = {'raw': 'not JSON'}
    elif fault == 'duplicate_id':
        data['listings'][0]['rows'].append(GUEST)
    elif fault == 'wrong_name':
        data['listings'][0]['rows'][0]['vm_name'] = 'foreign-guest'
    elif fault == 'template':
        data['listings'][0]['rows'][0]['template'] = 1
    elif fault in ('stop_error', 'delete_error'):
        command = 'stop_force' if fault == 'stop_error' else 'delete'
        data['failures'] = {f'proxmox_vm.vm_id.{command}.to.jsons.sh': 17}
    elif fault == 'post_error':
        data['listings'][1]['code'] = 18
    elif fault == 'post_malformed':
        data['listings'][1] = {'raw': 'not JSON'}
    elif fault == 'post_present':
        data['listings'][1]['rows'].append(GUEST)
    elif fault == 'ssh_destination':
        f['config'].write_text(f['config'].read_text().replace('192.168.142.250', '192.0.2.99'))
    elif fault == 'pin_race':
        data['race'] = 'new-foreign.example ' + f['public'] + '\n'
    update(f, **data)
    result, calls = run(f, entry)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not any(c['name'] == 'ansible-playbook' for c in calls)
    expected = before + (data['race'].encode() if fault == 'pin_race' else b'')
    assert f['pins'].read_bytes() == expected
    if fault in ('initial_error', 'initial_malformed', 'duplicate_id', 'wrong_name', 'template', 'ssh_destination'):
        assert all(c['name'] == 'proxmox_vm.list.to.jsons.sh' for c in calls)


@pytest.mark.parametrize('fault', ['symlink', 'hardlink', 'writable', 'multi_host', 'revoked', 'authority', 'wildcard'])
def test_unsafe_or_ambiguous_trust_is_refused_before_vm_mutations(tmp_path, fault):
    f = fixture(tmp_path)
    if fault == 'symlink':
        real = f['pins'].with_name('real-pins')
        f['pins'].rename(real)
        f['pins'].symlink_to(real)
    elif fault == 'hardlink':
        os.link(f['pins'], f['pins'].with_name('other-link'))
    elif fault == 'writable':
        f['pins'].chmod(0o666)
    else:
        value = {'multi_host': f['target'] + ',foreign.example', 'revoked': '@revoked ' + f['target'],
                 'authority': '@cert-authority ' + f['target'], 'wildcard': '*'}[fault]
        f['pins'].write_text(value + ' ' + f['public'] + '\n')
    before = f['pins'].read_bytes()
    result, calls = run(f)
    assert result.returncode != 0, result.stdout + result.stderr
    assert f['pins'].read_bytes() == before
    assert all(c['name'] == 'proxmox_vm.list.to.jsons.sh' for c in calls)


def test_hashed_exact_guest_target_can_retire_without_touching_other_hashes(tmp_path):
    f = fixture(tmp_path)
    subprocess.run(['ssh-keygen', '-H', '-f', str(f['pins'])], capture_output=True, check=True)
    before = f['pins'].read_text().splitlines(keepends=True)
    result, _ = run(f)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f['pins'].read_text().splitlines(keepends=True) == [before[0], before[2]]


def test_missing_pin_file_is_not_created_during_empty_first_deployment(tmp_path):
    f = fixture(tmp_path, initial=[], after=[])
    f['pins'].unlink()
    result, calls = run(f)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not f['pins'].exists()
    assert [c['name'] for c in calls] == ['proxmox_vm.list.to.jsons.sh'] * 2


def test_recreated_guest_stays_untrusted_until_independent_enrollment(tmp_path):
    """Real OpenSSH refuses both a stale key and the later unknown generation."""
    import importlib.util
    import io
    import socket
    import threading

    import paramiko
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    catalog_roles = os.environ.get('RANGE42_WORKSHOP_CATALOG_ROLES')
    if not catalog_roles:
        pytest.skip('Set the reviewed catalog role directory for independent enrollment acceptance')
    f = fixture(tmp_path)
    private = ed25519.Ed25519PrivateKey.generate()
    key = paramiko.Ed25519Key.from_private_key(io.StringIO(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()).decode()))
    public = private.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    stop, executed = threading.Event(), threading.Event()
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(3)
    listener.settimeout(0.2)
    port = listener.getsockname()[1]

    class Server(paramiko.ServerInterface):
        def check_auth_none(self, _name):
            return paramiko.AUTH_SUCCESSFUL

        def check_channel_request(self, kind, _channel):
            return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_exec_request(self, _channel, value):
            if value == b'true':
                executed.set()
                return True
            return False

    def serve():
        while not stop.is_set():
            try:
                client, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            transport = paramiko.Transport(client)
            try:
                transport.add_server_key(key)
                transport.start_server(server=Server())
                channel = transport.accept(2)
                if channel is not None and executed.wait(2):
                    channel.send_exit_status(0)
                    channel.close()
                    transport.join(timeout=3)
            except (EOFError, paramiko.SSHException):
                pass
            finally:
                transport.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    target = f'[127.0.0.1]:{port}'
    f['config'].write_text(f'Host r42.catalog-try-vm-docker\n HostName 127.0.0.1\n Port {port}\n GlobalKnownHostsFile /dev/null\n')
    path = f['scenario'] / 'manifest/scenario_vms.json'
    manifest = json.loads(path.read_text())
    manifest['vms'][0]['ip'] = '127.0.0.1'
    path.write_text(json.dumps(manifest))
    f['pins'].write_text('10.77.32.18 ' + f['public'] + '\n' + target + ' ' + f['public'] + '\n')
    argv = ['ssh', '-F', str(f['config']), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + str(f['pins']), '-o', 'ConnectTimeout=3', 'r42.catalog-try-vm-docker', 'true']
    try:
        stale = subprocess.run(argv, capture_output=True, text=True, timeout=8, check=False)
        assert stale.returncode == 255 and 'HOST IDENTIFICATION HAS CHANGED' in stale.stderr
        assert not executed.is_set()
        result, _ = run(f)
        assert result.returncode == 0, result.stdout + result.stderr
        unknown = subprocess.run(argv, capture_output=True, text=True, timeout=8, check=False)
        assert unknown.returncode == 255 and 'Host key verification failed' in unknown.stderr
        assert not executed.is_set()
        roles = Path(catalog_roles)
        module_path = roles / 'ansible.utils/library/range42_guest_hostkey_pin.py'
        assert module_path.is_file(), 'Configure the reviewed catalog runtime for independent enrollment'
        spec = importlib.util.spec_from_file_location('catalog_guest_pin', module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        state = module.inspect_known_hosts(f['pins'], target)
        assert not state['existing']
        # This fixture supplies the independently known public key. Production
        # obtains it only through the existing authenticated QGA ownership gates.
        module.append_known_host(f['pins'], target, public, state['state'])
        verified = subprocess.run(argv, capture_output=True, text=True, timeout=8, check=False)
        assert verified.returncode == 0, verified.stderr
        assert executed.is_set()
        assert f['pins'].read_text().startswith('10.77.32.18 ' + f['public'] + '\n')
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=3)


def test_nonregular_trust_cannot_block_the_native_lifecycle(tmp_path):
    f = fixture(tmp_path)
    f['pins'].unlink()
    os.mkfifo(f['pins'], mode=0o600)
    result = subprocess.run(['bash', str(f['scenario'] / 'catalog_try.delete_vms_only.sh')],
        cwd=f['scenario'], env=f['env'], capture_output=True, text=True, timeout=2, check=False)
    assert result.returncode != 0
    calls = [json.loads(line) for line in f['calls'].read_text().splitlines()]
    assert all(c['name'] == 'proxmox_vm.list.to.jsons.sh' for c in calls)
