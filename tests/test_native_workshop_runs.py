"""Exercise dynamic native workshop ownership and inventory with real inputs."""
import importlib.util
import json
import subprocess
import os
import sys
import ssl
from pathlib import Path

import jinja2
import pytest
import yaml
from test_vm_bootstrap_unlock_api import certificate as certificate, endpoint as endpoint, SECRET

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / 'scenarios/native_install_workshop'


def module(name, relative):
    specification = importlib.util.spec_from_file_location(name, SCENARIO / relative)
    value = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(value)
    return value


def allocation():
    return {'vm_id': 45000, 'vm_name': 'course-user01-pve', 'username': 'user01', 'seat': 1,
        'role': 'proxmox', 'owner': 'range42-workshop:' + 'a' * 16 + ':user01:proxmox',
        'ip': '10.78.0.2', 'gateway': '10.78.0.1', 'prefix': 28, 'bridge': 'vmbr600',
        'memory_mib': 16384, 'cores': 4, 'storage': 'fast-storage', 'alias': 'r42.course.user01.proxmox'}


def live_config(expected):
    return {'name': expected['vm_name'], 'description': expected['owner'],
        'vmgenid': '12345678-1234-1234-1234-123456789abc', 'cpu': 'host',
        'memory': 16384, 'cores': 4, 'ipconfig0': 'ip=10.78.0.2/28,gw=10.78.0.1',
        'net0': 'virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr600',
        'scsi0': 'fast-storage:vm-45000-disk-0,size=32G',
        'scsi1': 'fast-storage:vm-45000-disk-1,size=128G',
        'ide2': 'fast-storage:vm-45000-cloudinit,media=cdrom'}


def test_dynamic_workshop_retains_generation_proof_without_fixed_friday_ids():
    plugin = module('workshop_run_filter', 'filter_plugins/workshop.py')
    expected = allocation()
    current = live_config(expected)
    receipt = {'owner': expected['owner'], 'vmid': expected['vm_id'], 'vmgenid': current['vmgenid']}
    assert plugin.verify(current, expected, receipt) is True
    for key, value in {'vmgenid': 'abcdefab-1234-1234-1234-123456789abc',
        'description': expected['owner'].replace('a' * 16, 'b' * 16),
        'net0': 'virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr601',
        'scsi0': 'fast-storage:vm-45001-disk-0,size=32G', 'args': '-unsafe', 'template': 1}.items():
        with pytest.raises(ValueError):
            plugin.verify({**current, key: value}, expected, receipt)
    with pytest.raises(ValueError):
        plugin.verify(current, expected, {**receipt, 'vmid': 45001})
    assert plugin.retirement_state(None, expected, {**receipt, 'phase': 'retiring'}, True)
    with pytest.raises(ValueError):
        plugin.retirement_state(None, expected, receipt, True)


def test_partial_cleanup_never_adopts_a_live_guest_without_an_original_receipt():
    plugin = module('workshop_partial_filter', 'filter_plugins/workshop.py')
    expected = allocation()
    absent = {'owner': expected['owner'], 'vmid': expected['vm_id'], 'phase': 'uncreated'}
    assert plugin.retirement_state(None, expected, absent, True)
    with pytest.raises(ValueError):
        plugin.retirement_state(live_config(expected), expected, absent, True)
    with pytest.raises(ValueError):
        plugin.retirement_state(None, expected, absent, False)
    with pytest.raises(ValueError):
        plugin.retirement_state(None, expected, {**absent, 'owner': 'foreign'}, True)


def test_inventory_is_rendered_from_the_same_run_plan_with_no_installation_literals():
    guest = allocation()
    template = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(
        (SCENARIO / 'templates/ansible-inventory.j2').read_text())
    rendered = template.render(INFRASTRUCTURE_CODENAME='selected', INFRASTRUCTURE_PROXMOX_ADDRESS='192.0.2.10',
        range42_workshop_plan={'guests': [guest]}, range42_workshop_known_hosts='/private/context/ssh_keys/known_hosts')
    document = yaml.safe_load(rendered)
    assert document['all']['children']['proxmox']['hosts']['selected']['ansible_host'] == '192.0.2.10:8006'
    assert document['all']['children']['workshop_guests']['hosts'][guest['alias']]['workshop_guest'] == guest
    assert 'pve42' not in rendered and '10.77.32' not in rendered and '20261023' not in rendered
    metadata = json.loads((SCENARIO / 'manifest/workshop.json').read_text())
    assert metadata['kind'] == 'native-installation'
    assert json.loads((SCENARIO / 'manifest/scenario_vms.json').read_text())['vms'] == []


def test_native_participant_ui_uses_its_verified_run_marker_instead_of_inferred_addresses():
    helper = module('workshop_run_ui', 'files/workshop_ui.py')
    guest = allocation()
    marker = {**guest, 'role': 'deployer', 'owner': guest['owner'].replace(':proxmox', ':deployer'),
        'proxmox_address': '10.78.0.2', 'proxmox_node': 'course-user01-pve',
        'expires_at': '2030-10-23T18:00:00Z'}
    human = {'proxmox_api_host': '10.78.0.2:8006', 'proxmox_node': 'course-user01-pve',
             'proxmox_dest_vm_storage_name': 'local-lvm'}
    result = helper.specification(marker, human, 'course01')
    assert result['address'] == '10.78.0.2' and result['node'] == 'course-user01-pve'
    with pytest.raises(ValueError):
        helper.specification(marker, {**human, 'proxmox_api_host': '10.78.0.18:8006'}, 'course01')
    with pytest.raises(ValueError):
        helper.specification({**marker, 'owner': 'foreign'}, human, 'course01')


def test_retirement_releases_only_a_declared_endpoint_and_the_original_pin(tmp_path):
    pin = module('workshop_run_pin', 'library/workshop_hostkey.py')
    tmp_path.chmod(0o700)
    key_path = tmp_path / 'key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key_path)], check=True)
    public = ' '.join(key_path.with_suffix('.pub').read_text().split()[:2])
    known = tmp_path / 'known_hosts'
    known.write_text(f'10.78.0.2 {public}\n10.78.0.18 {public}\n')
    known.chmod(0o600)
    assert pin.process(known, 'capture', '10.78.0.2', None, ['10.78.0.2'])['key'] == public
    with pytest.raises(ValueError):
        pin.process(known, 'remove', '10.78.0.18', public, ['10.78.0.2'])
    with pytest.raises(ValueError):
        pin.process(known, 'remove', '10.78.0.2', 'foreign', ['10.78.0.2'])
    assert pin.process(known, 'remove', '10.78.0.2', public, ['10.78.0.2'])['changed'] is True
    assert known.read_text() == f'10.78.0.18 {public}\n'


@pytest.mark.parametrize('entrypoint', ['main.yml', 'configure.yml', 'reset.yml', 'teardown.yml'])
def test_native_entrypoints_parse_with_the_reviewed_runtime_roles(tmp_path, entrypoint):
    controller = os.environ.get('RANGE42_WORKSHOP_CONTROLLER_ROLES')
    catalog = os.environ.get('RANGE42_WORKSHOP_CATALOG_ROLES')
    if not controller or not catalog:
        pytest.skip('Set the reviewed controller/catalog role directories for native syntax acceptance')
    context = tmp_path / 'context'
    (context / 'secrets').mkdir(parents=True)
    (context / 'secrets/default_vault.yml').write_text('{}\n')
    inventory = tmp_path / 'inventory.yml'
    inventory.write_text('all:\n  children:\n    proxmox:\n      hosts:\n        selected:\n          ansible_connection: local\n    workshop_guests:\n      hosts: {}\n')
    result = subprocess.run([sys.executable, '-m', 'ansible.cli.playbook', '--syntax-check', '-i', str(inventory),
        str(SCENARIO / entrypoint)], env={**os.environ, 'RANGE42_ACTIVE_CONFIG_DIR': str(context),
        'ANSIBLE_ROLES_PATH': controller + ':' + catalog}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('fault', [None, 'sealed', 'wrong_disks', 'passthrough', 'missing_nic', 'malformed_nic', 'extra_nic', 'untrusted_certificate'])
def test_real_native_template_gate_blocks_unsafe_sources_without_disclosing_credentials(tmp_path, endpoint, fault):
    replies = []
    for template in (9230, 9222):
        config = {'template': 1, 'cpu': 'host', 'agent': 'enabled=1',
            'net0': 'virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr422',
            'scsi0': f'pool:base-{template}-disk-0,size=32G', 'ide2': f'pool:vm-{template}-cloudinit,media=cdrom'}
        if template == 9230:
            config['scsi1'] = f'pool:base-{template}-disk-1,size=128G'
        if fault == 'wrong_disks':
            config['scsi0'] = f'pool:base-{template}-disk-0,size=24G'
        if fault == 'passthrough':
            config['hostpci0'] = '0000:01:00.0'
        if fault in ('missing_nic', 'sealed'):
            config.pop('net0')
        if fault == 'missing_nic':
            config['ipconfig0'] = 'ip=192.0.2.2/24,gw=192.0.2.1'
        if fault == 'extra_nic':
            config['net1'] = 'virtio=AA:BB:CC:DD:EE:01,bridge=vmbr422'
        elif fault == 'malformed_nic':
            config['net0'] = 'virtio=not-a-mac,bridge=vmbr422'
        replies.append((200, {'data': config}))
    endpoint['replies'].clear()
    endpoint['replies'].extend(replies)
    context = tmp_path / 'context'
    (context / 'secrets').mkdir(parents=True)
    (context / 'secrets/default_vault.yml').write_text(yaml.safe_dump({
        'proxmox_api_host': endpoint['host'], 'proxmox_node': 'node-a', 'proxmox_api_user': 'fixture@pve',
        'proxmox_api_token_id': 'scoped', 'proxmox_api_token_secret': SECRET}))
    inventory = tmp_path / 'hosts.yml'
    inventory.write_text(yaml.safe_dump({'all': {'children': {'proxmox': {'hosts': {'fixture': {
        'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable}}}}}}))
    variables = tmp_path / 'variables.json'
    variables.write_text(json.dumps({'range42_workshop_plan': {'proxmox_template': 9230, 'deployer_template': 9222}}))
    result = subprocess.run([sys.executable, '-m', 'ansible.cli.playbook', '-i', str(inventory),
        str(SCENARIO / 'validate-templates.yml'), '--extra-vars', '@' + str(variables)],
        env={**os.environ, 'RANGE42_ACTIVE_CONFIG_DIR': str(context),
            'SSL_CERT_FILE': endpoint['ca'] if fault != 'untrusted_certificate' else ssl.get_default_verify_paths().openssl_cafile,
            'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'ansible-tmp')},
        capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) == (fault in (None, 'sealed')), result.stdout + result.stderr
    assert SECRET not in result.stdout + result.stderr
    if fault == 'untrusted_certificate':
        assert not endpoint['requests']
    else:
        assert len(endpoint['requests']) == 2


@pytest.mark.parametrize('fault', [None, 'live_without_receipt', 'hidden_foreign'])
def test_real_ansible_partial_cleanup_requires_independent_absence_before_skipping_uncreated_vm(tmp_path, endpoint, fault):
    guest = allocation()
    endpoint['replies'].clear()
    endpoint['replies'].extend([(200, {'data': live_config(guest)})] if fault == 'live_without_receipt' else
        [(500, {'message': 'VM does not exist'}),
         (400, {'errors': {'vmid': 'already exists'}}) if fault == 'hidden_foreign' else (200, {'data': guest['vm_id']})])
    receipts = tmp_path / 'receipts'
    receipts.mkdir(mode=0o700)
    playbook = tmp_path / 'check.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': {'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
            'workshop_guest': guest, 'workshop_allow_retired': True, 'workshop_receipt_root': str(receipts),
            'proxmox_api_host': endpoint['host'], 'proxmox_node': 'node-a', 'proxmox_api_user': 'fixture@pve',
            'proxmox_api_token_id': 'scoped', 'proxmox_api_token_secret': SECRET},
        'tasks': [{'ansible.builtin.import_tasks': str(SCENARIO / 'tasks/owned.yml')},
            {'ansible.builtin.assert': {'that': ['workshop_guest_absent | bool', 'workshop_guest_uncreated | bool']}}]}]))
    result = subprocess.run([sys.executable, '-m', 'ansible.cli.playbook', '-i', 'localhost,', str(playbook)],
        env={**os.environ, 'SSL_CERT_FILE': endpoint['ca'], 'ANSIBLE_FILTER_PLUGINS': str(SCENARIO / 'filter_plugins'), 'ANSIBLE_LIBRARY': str(SCENARIO / 'library'),
            'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'ansible-tmp')}, capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) == (fault is None), result.stdout + result.stderr
    assert SECRET not in result.stdout + result.stderr
    assert all('/config' in request['path'] or '/cluster/nextid' in request['path'] for request in endpoint['requests'])
    assert list(receipts.iterdir()) == []  # Absence is never invented into an original clone receipt.


def test_sealed_clone_resumes_only_from_its_recorded_empty_network():
    plugin = module('workshop_sealed_filter', 'filter_plugins/workshop.py')
    expected = allocation()
    final = live_config(expected)
    sealed = {key: value for key, value in final.items() if key not in ('net0', 'ipconfig0')}
    receipt = {'owner': expected['owner'], 'vmid': expected['vm_id'], 'vmgenid': final['vmgenid'],
        'bootstrap_network': {'net0': None, 'ipconfig0': None}}
    assert plugin.verify_bootstrap(sealed, expected, receipt)
    assert plugin.needs_cloudinit(sealed, expected, receipt)
    assert plugin.verify_bootstrap(final, expected, receipt)
    assert not plugin.needs_cloudinit(final, expected, receipt)
    for changes in [
        {'net0': 'virtio=AA:BB:CC:DD:EE:01,bridge=vmbr601'},
        {'net1': 'virtio=AA:BB:CC:DD:EE:01,bridge=vmbr600'},
        {'ipconfig0': 'ip=192.0.2.2/24'},
        {'net0': None},
        {'vmgenid': 'abcdefab-1234-1234-1234-123456789abc'},
        {'memory': 32768},
    ]:
        with pytest.raises(ValueError):
            plugin.verify_bootstrap({**sealed, **changes}, expected, receipt)
    with pytest.raises(ValueError):
        plugin.verify_bootstrap(sealed, expected, {**receipt, 'bootstrap_complete': True})


@pytest.mark.parametrize('sealed', [False, True])
def test_actual_clone_generation_receipt_records_network_before_first_configuration(tmp_path, sealed):
    guest = allocation()
    current = live_config(guest)
    if sealed:
        current.pop('net0')
        current.pop('ipconfig0')
    tasks = yaml.safe_load((SCENARIO / 'tasks/clone-one.yml').read_text())
    receipt_task = next(task for task in tasks if task.get('name') == 'Record the owned generation before the first hardware change')
    playbook = tmp_path / 'receipt.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': {'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
            'workshop_guest': guest, 'workshop_receipt_root': str(tmp_path),
            'workshop_clone': {'json': {'data': current}}}, 'tasks': [receipt_task]}]))
    result = subprocess.run([sys.executable, '-m', 'ansible.cli.playbook', '-i', 'localhost,', str(playbook)],
        env={**os.environ, 'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'ansible-tmp')},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((tmp_path / f"{guest['vm_id']}.json").read_text())
    assert receipt['vmgenid'] == current['vmgenid'] and receipt['owner'] == guest['owner']
    assert receipt['bootstrap_network'] == {'net0': current.get('net0'), 'ipconfig0': current.get('ipconfig0')}
    assert (tmp_path / f"{guest['vm_id']}.json").stat().st_mode & 0o777 == 0o600
