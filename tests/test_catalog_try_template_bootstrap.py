"""Exercise the template-only boundary through TLS and native Ansible."""
import datetime
import http.server
import ipaddress
import json
import os
import shutil
import ssl
import subprocess
import threading
from pathlib import Path

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
IMPORTS = [
    './_firewall/stage_00-pre_scenario.report_status.yml',
    './_firewall/stage_01-pre_scenario.management_access.yml',
    './00_sdn_bootstrap/_main.yml',
    './01_init_proxmox/templates/_main_download_cloudinit_files.yml',
    './01_init_proxmox/templates/ubuntu_noble/_main_ubuntu_noble.yml',
]


@pytest.fixture
def fixture(tmp_path):
    scenario = tmp_path / 'catalog_try'
    shutil.copytree(ROOT / 'scenarios/catalog_try', scenario)
    binary = tmp_path / 'bin'
    binary.mkdir()
    calls = tmp_path / 'calls.jsonl'
    recorder = binary / 'ansible-playbook'
    recorder.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
        'with open(os.environ["TEST_CALLS"],"a") as f:f.write(json.dumps(sys.argv[1:])+"\\n")\n')
    recorder.chmod(0o700)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.datetime.now(datetime.UTC)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
        .sign(key, hashes.SHA256()))
    ca, private = tmp_path / 'ca.pem', tmp_path / 'key.pem'
    ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    state = {'rows': [], 'config': {'name': 'template-vm-small-01-4g-32g', 'template': 1},
        'requests': [], 'status': 200}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests'].append(self.path)
            assert self.headers.get('Authorization') == 'PVEAPIToken=fixture@pve!fixture=fixture-value'
            if self.path.endswith('/qemu'):
                data = state['rows']
            elif self.path.endswith('/qemu/9221/config'):
                data = state['config']
            else:
                self.send_error(404)
                return
            self.send_response(state['status'])
            if state['status'] == 302:
                self.send_header('Location', self.path)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'data': data}).encode())

        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    secret_dir = tmp_path / 'context/secrets'
    secret_dir.mkdir(parents=True)
    vault = secret_dir / 'default_vault.yml'
    vault.write_text(yaml.safe_dump({'proxmox_api_host': '127.0.0.1:' + str(server.server_port),
        'proxmox_node': 'owned-node', 'proxmox_api_user': 'fixture@pve',
        'proxmox_api_token_id': 'fixture', 'proxmox_api_token_secret': 'fixture-value'}))
    password = secret_dir / 'vault_pass.txt'
    password.write_text('fixture-vault-passphrase\n')
    subprocess.run(['ansible-vault', 'encrypt', str(vault), '--vault-password-file', str(password)],
        check=True, capture_output=True)
    env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
        'RANGE42_ACTIVE_CONFIG_DIR': str(secret_dir.parent), 'RANGE42_VAULT_PASSWORD_FILE': str(password),
        'RANGE42_ANSIBLE_ROLES__INVENTORY_DIR': str(tmp_path / 'inventory'),
        'RANGE42_PROXMOX_CA_FILE': str(ca), 'TEST_CALLS': str(calls)}
    yield {'scenario': scenario, 'calls': calls, 'env': env, 'state': state, 'binary': binary}
    server.shutdown()
    worker.join(timeout=3)
    server.server_close()


def run(f, args=()):
    result = subprocess.run(['bash', str(f['scenario'] / 'catalog_try.setup_templates_only.sh'), *args],
        cwd=f['scenario'], env=f['env'], capture_output=True, text=True, timeout=30, check=False)
    calls = [json.loads(x) for x in f['calls'].read_text().splitlines()] if f['calls'].exists() else []
    return result, calls


def test_empty_native_target_runs_only_template_playbook(fixture):
    result, calls = run(fixture, ['--check', '--diff'])
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls) == 1
    assert any(Path(arg).name == 'main_templates_only.yml' for arg in calls[0])
    assert calls[0][-2:] == ['--check', '--diff']
    assert fixture['state']['requests'] == ['/api2/json/nodes/owned-node/qemu']


def test_retained_exact_native_template_is_read_only(fixture):
    fixture['state']['rows'] = [{'vmid': 9221, 'name': 'template-vm-small-01-4g-32g', 'template': 1}]
    before = dict(fixture['state']['config'])
    result, calls = run(fixture)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not calls
    assert fixture['state']['config'] == before
    assert fixture['state']['requests'][-1].endswith('/9221/config')


@pytest.mark.parametrize('fault', ['wrong_name', 'not_template', 'http_error', 'malformed', 'duplicate', 'untrusted_tls', 'redirect'])
def test_unowned_or_unverified_target_stops_before_any_mutation(fixture, fault):
    state = fixture['state']
    state['rows'] = [{'vmid': 9221}]
    if fault == 'wrong_name':
        state['config']['name'] = 'foreign-template'
    elif fault == 'not_template':
        state['config']['template'] = 0
    elif fault == 'http_error':
        state['status'] = 500
    elif fault == 'malformed':
        state['rows'] = {'vmid': 9221}
    elif fault == 'duplicate':
        state['rows'] *= 2
    elif fault == 'redirect':
        state['status'] = 302
    else:
        fixture['env'].pop('RANGE42_PROXMOX_CA_FILE')
    result, calls = run(fixture)
    assert result.returncode != 0
    assert not calls
    assert 'fixture-value' not in result.stdout + result.stderr
    if fault == 'redirect':
        assert len(state['requests']) == 1


@pytest.mark.parametrize('args', [['-e', 'vm_id=1250'], ['--extra-vars=@foreign.yml'],
    ['-i', 'foreign-inventory'], ['--vault-password-file', 'foreign-pass']])
def test_template_boundary_refuses_provider_and_inventory_overrides(fixture, args):
    result, calls = run(fixture, args)
    assert result.returncode != 0
    assert not calls
    assert not fixture['state']['requests']


def test_invalid_native_vault_yaml_has_only_fixed_private_safe_diagnostic(fixture):
    context = Path(fixture['env']['RANGE42_ACTIVE_CONFIG_DIR'])
    vault = context / 'secrets/default_vault.yml'
    vault.write_text('broken: [fixture-private-parser-value')
    subprocess.run(['ansible-vault', 'encrypt', str(vault), '--vault-password-file',
        fixture['env']['RANGE42_VAULT_PASSWORD_FILE']], check=True, capture_output=True)
    result, calls = run(fixture)
    assert result.returncode != 0
    assert not calls
    assert not fixture['state']['requests']
    assert 'fixture-private-parser-value' not in result.stdout + result.stderr
    assert 'Traceback' not in result.stdout + result.stderr


def test_template_only_composition_executes_real_ansible_without_guest_stages(fixture, tmp_path):
    playbook = fixture['scenario'] / 'main_templates_only.yml'
    assert playbook.is_file(), 'A bounded template-only entry point is required'
    document = yaml.safe_load(playbook.read_text())
    assert [play['import_playbook'] for play in document] == IMPORTS
    inventory = tmp_path / 'inventory'
    inventory.mkdir()
    (inventory / 'inventory_default.yml').write_text('all:\n  hosts:\n    localhost:\n      ansible_connection: local\n')
    fixture['env']['RANGE42_ANSIBLE_ROLES__INVENTORY_DIR'] = str(inventory)
    fixture['env']['PATH'] = os.environ['PATH']
    markers = tmp_path / 'stages.jsonl'
    for index, imported in enumerate(IMPORTS):
        path = fixture['scenario'] / imported
        path.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'tasks': [{
            'name': 'Record fixed native template stage', 'ansible.builtin.lineinfile': {
                'path': str(markers), 'line': str(index), 'create': True, 'mode': '0600'}}]}]))
    result, _ = run(fixture)
    assert result.returncode == 0, result.stdout + result.stderr
    assert markers.read_text().splitlines() == ['0', '1', '2', '3', '4']


def test_native_creation_recipe_declares_only_template_9221():
    root = ROOT / 'scenarios/catalog_try/01_init_proxmox/templates/ubuntu_noble'
    assert yaml.safe_load((root / '_main_ubuntu_noble.yml').read_text()) == [
        {'import_playbook': './02-template-vm-small-01-4g-32g.yml'}]
    plays = yaml.safe_load((root / '02-template-vm-small-01-4g-32g.yml').read_text())
    actions = [task['vars'] for play in plays for task in play['tasks']]
    assert {value['vm_id'] for value in actions} == {9221}
    assert {value['proxmox_vm_action'] for value in actions} == {
        'vm_create', 'template_convert_vm_to_template', 'template_cloudinit_import_disk',
        'cloudinit_set_variables', 'vm_set_tag'}
    assert all('vm_new_id' not in value for value in actions)
