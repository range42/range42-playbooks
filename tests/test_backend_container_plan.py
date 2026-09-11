"""Installer plans preserve bindings and reject ambiguous inputs before writes."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / 'bundles/admin/software.install.deployer_api_backend/files/container_plan.py'


def module():
    assert FILE.exists(), 'managed installer needs a validated plan before provisioning'
    spec = importlib.util.spec_from_file_location('container_plan', FILE)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def config(tmp_path):
    return {'root': str(tmp_path / 'install'), 'name': 'fixture-api',
            'image': 'sha256:' + 'a' * 64, 'uid': os.getuid(), 'gid': os.getgid()}


def test_fresh_plan_is_deterministic_and_does_not_create_state(tmp_path):
    raw = config(tmp_path)
    plan = module().validate_config(raw)
    assert plan == module().validate_config(raw)
    assert not (tmp_path / 'install').exists()
    assert plan['database_host'] == str(tmp_path / 'install/state/workspaces/.range42.db')
    assert plan['workspace_container'] == '/var/lib/range42/workspaces'


@pytest.mark.parametrize('change', [
    {'image': 'backend:latest'}, {'unknown': True}, {'uid': True}, {'port': 0},
    {'name': 'bad/name'}, {'listen_address': '$(unsafe)'}, {'root': 'relative'},
    {'workspace_container': '/run/secrets'}, {'database_container': '/elsewhere/db'},
    {'cors_origins': ['https://ui.example/path']},
])
def test_invalid_configuration_is_rejected_without_creating_state(tmp_path, change):
    with pytest.raises(ValueError):
        module().validate_config({**config(tmp_path), **change})
    assert not (tmp_path / 'install').exists()


def test_original_legacy_workspace_and_database_paths_are_explicitly_preserved(tmp_path):
    plan = module().validate_config({**config(tmp_path),
        'workspace_host': str(tmp_path / 'old-workspaces'),
        'workspace_container': '/home/range42/range42.config',
        'database_container': '/home/range42/range42.config/.old.db'})
    assert plan['database_host'] == str(tmp_path / 'old-workspaces/.old.db')
    compose = module().compose_document(plan, 'b' * 64)
    service = compose['services']['api']
    assert service['environment']['RANGE42_WORKSPACE_ROOT'] == '/home/range42/range42.config'
    assert service['environment']['RANGE42_DB_URL'] == 'sqlite+aiosqlite:////home/range42/range42.config/.old.db'
    assert any(mount['source'] == str(tmp_path / 'old-workspaces') and mount['target'] == '/home/range42/range42.config' for mount in service['volumes'])
    assert service['read_only'] and service['init'] and service['user'] == f'{os.getuid()}:{os.getgid()}'
    assert 'SSH_KEY_PATH' not in json.dumps(compose) and '/home/range42/.ssh' not in json.dumps(compose)
    assert service['environment']['RANGE42_AUTH_MODE'] == 'required'
    assert 'RANGE42_API_TOKEN' not in service['environment']


def test_runtime_mounts_cover_pinned_dependencies_and_private_template(tmp_path):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    template = tmp_path / 'template'
    template.mkdir()
    plan = module().validate_config({**config(tmp_path), 'runtime_dir': str(runtime),
                                    'workspace_template_dir': str(template)})
    service = module().compose_document(plan, 'b' * 64)['services']['api']
    mounts = {mount['target']: mount for mount in service['volumes']}
    assert mounts['/runtime']['read_only'] and not mounts['/runtime']['bind']['create_host_path']
    assert mounts['/run/range42-template']['read_only']
    assert service['environment']['RANGE42_INVENTORY__DOCKER__CTF'].endswith('/docker/_ctf')
    assert service['environment']['RANGE42_PROXMOX_CA_FILE'] == '/runtime/proxmox-ca.pem'
    assert len(service['environment']['ANSIBLE_ROLES_PATH'].split(':')) == 4


def test_symlinked_host_paths_cannot_redirect_installer_state(tmp_path):
    destination = tmp_path / 'elsewhere'
    destination.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match='symbolic|symlink'):
        module().validate_config({**config(tmp_path), 'state_dir': str(alias)})


@pytest.mark.parametrize('binding', ['state_contains_installation', 'workspace_contains_installation', 'credentials_writable_through_state'])
def test_writable_mounts_cannot_expose_installer_records_or_credentials(tmp_path, binding):
    raw = config(tmp_path)
    if binding == 'state_contains_installation':
        raw['state_dir'] = str(tmp_path)
    elif binding == 'workspace_contains_installation':
        raw['workspace_host'] = str(tmp_path)
    else:
        raw['secrets_dir'] = raw['root'] + '/state/secrets'
    with pytest.raises(ValueError, match='writable|overlap'):
        module().validate_config(raw)
