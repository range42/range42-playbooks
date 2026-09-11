"""The managed consumer preserves unknown state and immutable release bytes."""
import importlib.util
import os
from pathlib import Path
import sys

import pytest

FILES = Path(__file__).resolve().parents[1] / 'bundles/admin/software.install.deployer_api_backend/files'


def consumer():
    file = FILES / 'container_apply.py'
    assert file.is_file(), 'The real bundle needs a managed installer consumer'
    sys.path.insert(0, str(FILES))
    try:
        spec = importlib.util.spec_from_file_location('container_apply', file)
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result
    finally:
        sys.path.remove(str(FILES))


def config(tmp_path):
    return {'root': str(tmp_path / 'installation'), 'name': 'consumer-test',
            'image': 'sha256:' + 'a' * 64, 'uid': os.getuid(), 'gid': os.getgid()}


def test_invalid_request_does_not_create_installation(tmp_path):
    module = consumer()
    with pytest.raises(ValueError, match='immutable'):
        module.apply({**config(tmp_path), 'image': 'backend:latest'})
    assert not (tmp_path / 'installation').exists()


def test_unknown_installation_never_adopts_or_rewrites_legacy_data(tmp_path):
    module = consumer()
    root = tmp_path / 'installation'
    root.mkdir()
    old = root / 'docker-compose.yml'
    old.write_text('legacy: keep\n')
    with pytest.raises(ValueError, match='unmanaged|unknown|legacy'):
        module.apply(config(tmp_path))
    assert old.read_text() == 'legacy: keep\n'
    assert not (root / 'secrets').exists()


def test_existing_external_workspace_is_not_treated_as_fresh(tmp_path):
    module = consumer()
    workspace = tmp_path / 'historical-workspaces'
    workspace.mkdir()
    history = workspace / 'events.jsonl'
    history.write_text('historical artifact\n')
    with pytest.raises(ValueError, match='existing|adoption'):
        module.apply({**config(tmp_path), 'workspace_host': str(workspace)})
    assert history.read_text() == 'historical artifact\n'
    assert not (tmp_path / 'installation/secrets').exists()


def test_installation_lock_serializes_and_never_replaces_its_inode(tmp_path):
    module = consumer()
    root = tmp_path / 'installation'
    root.mkdir(mode=0o700)
    with module.installation_lock(root):
        inode = (root / '.installation.lock').stat().st_ino
        with pytest.raises(ValueError, match='busy'):
            with module.installation_lock(root):
                pytest.fail('Concurrent installer entered')
    assert (root / '.installation.lock').stat().st_ino == inode


def test_lock_symlink_is_not_followed(tmp_path):
    module = consumer()
    root = tmp_path / 'installation'
    root.mkdir()
    victim = tmp_path / 'victim'
    victim.write_text('keep')
    (root / '.installation.lock').symlink_to(victim)
    with pytest.raises((ValueError, OSError)):
        with module.installation_lock(root):
            pytest.fail('Symlink lock accepted')
    assert victim.read_text() == 'keep'


def test_staged_tree_preserves_literal_links_and_refuses_escape(tmp_path):
    module = consumer()
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'file').write_bytes(b'\x00\xff\n')
    (source / 'link').symlink_to('./file')
    staged = tmp_path / 'staged'
    expected = module.tree_hash(source)
    module.copy_tree(source, staged, uid=os.getuid(), gid=os.getgid())
    assert module.tree_hash(staged) == expected
    assert os.readlink(staged / 'link') == './file'
    (source / 'escape').symlink_to('../outside')
    (tmp_path / 'outside').write_text('do not copy')
    with pytest.raises(ValueError, match='link'):
        module.tree_hash(source)


def test_special_files_are_rejected_before_copy(tmp_path):
    module = consumer()
    source = tmp_path / 'source'
    source.mkdir()
    os.mkfifo(source / 'pipe')
    with pytest.raises(ValueError, match='special'):
        module.tree_hash(source)
