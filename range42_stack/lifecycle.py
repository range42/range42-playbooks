"""Private state backup/restore and ownership checks for native lifecycle bundles.

VM disks are backed up separately with Proxmox vzdump while all stack VMs are
stopped. A state archive alone is NOT a database or attachment backup.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import ssl
import sys
import tarfile
import tempfile
import uuid

from .install import private_write, request_json


def backup_state(instance, archive):
    instance, archive = Path(instance), Path(archive)
    if archive.resolve().is_relative_to(instance.resolve()):
        raise ValueError('Backup must be outside the live staging directory')
    files = {}
    for path in sorted(instance.rglob('*')):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError('State backups cannot contain links or special files')
        if path.is_file():
            with path.open('rb') as stream:
                files[path.relative_to(instance).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    if 'release.json' not in files:
        raise ValueError('State backup requires a release record')
    archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as tar:
            for name in files:
                tar.add(instance / name, arcname=name, recursive=False)
            data = json.dumps({'version': 1, 'instance': instance.name, 'files': files}, sort_keys=True).encode()
            info = tarfile.TarInfo('.state-backup.json'); info.size = len(data); info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    except BaseException:
        archive.unlink(missing_ok=True)
        raise


def _validate_archive(tar):
    names = set()
    for item in tar.getmembers():
        if (not item.isfile() or item.name in names or PurePosixPath(item.name).is_absolute()
                or any(p in {'', '.', '..'} for p in item.name.split('/')) or '\\' in item.name):
            raise ValueError('Invalid state backup path or member')
        names.add(item.name)
    try:
        manifest = json.load(tar.extractfile('.state-backup.json'))
        if manifest['version'] != 1 or set(manifest['files']) != names - {'.state-backup.json'}:
            raise ValueError()
        for name, expected in manifest['files'].items():
            with tar.extractfile(name) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ValueError('State backup integrity check failed') from None
    return manifest


def restore_state(archive, destination):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    with tarfile.open(archive) as tar:
        manifest = _validate_archive(tar)
        if manifest['instance'] != destination.name:
            raise ValueError('Backup belongs to a different instance')
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.restore-') as temp:
            root = Path(temp)
            tar.extractall(root, members=[m for m in tar.getmembers() if m.name != '.state-backup.json'], filter='data')
            for path in root.rglob('*'):
                path.chmod(0o700 if path.is_dir() or path.stat().st_mode & 0o111 else 0o600)
            root.rename(destination)


def authorize_upgrade(instance, revisions, backup):
    instance = Path(instance)
    with tarfile.open(backup) as tar:
        manifest = _validate_archive(tar)
        if (manifest['instance'] != instance.name or json.load(tar.extractfile('release.json')) !=
                json.loads((instance / 'release.json').read_text())):
            raise ValueError('Upgrade requires a backup of the current instance release')
    private_write(instance / 'previous-release.json', (instance / 'release.json').read_text())
    private_write(instance / 'release.json', json.dumps(revisions, sort_keys=True))


def rollback_state(instance, archive):
    """Validate/extract first, retain failed state, then restore the saved release."""
    instance = Path(instance)
    if instance.is_symlink() or not instance.is_dir():
        raise ValueError('Rollback requires an existing instance directory')
    with tempfile.TemporaryDirectory(dir=instance.parent, prefix='.rollback-') as temp:
        restored = Path(temp) / instance.name
        restore_state(archive, restored)
        for marker in restored.glob('*/owner.json'):
            current = instance / marker.relative_to(restored)
            if not current.is_file() or current.read_bytes() != marker.read_bytes():
                raise ValueError('Rollback backup belongs to a different stack plan')
        failed = instance.with_name(instance.name + '.before-rollback-' + uuid.uuid4().hex[:12])
        instance.rename(failed)
        try:
            restored.rename(instance)
        except BaseException:
            failed.rename(instance)
            raise
    return failed


def validate_action(plan, resources, action, confirmation):
    if action not in {'checkpoint', 'backup', 'rollback', 'teardown', 'restore', 'stop', 'start'}:
        raise ValueError('Unknown platform lifecycle action')
    if confirmation != plan['id']:
        raise ValueError('Lifecycle action requires the exact stack ID')
    owned = {int(v['vmid']): v for v in resources}
    for vm in plan['vms']:
        actual = owned.get(vm['vm_id'])
        if not actual:
            if action == 'restore':
                continue
            raise ValueError('Cannot verify ownership of every stack VM')
        if (actual.get('name') != vm['vm_name'] or actual.get('node') != plan['node']
                or actual.get('config', {}).get('description') != 'range42-stack:' + plan['id']
                or actual.get('type', 'qemu') != 'qemu' or actual.get('config', {}).get('template')):
            raise ValueError('Live VM ownership does not match the stack plan')
        if action == 'restore':
            raise ValueError('Restore requires absent VMIDs; never overwrite an existing VM')
        if action in {'checkpoint', 'backup', 'rollback', 'teardown'} and actual.get('status') != 'stopped':
            raise ValueError('All stack VMs must be stopped for this action')


def live_guard(plan, runtime, parent, action, confirmation):
    from .scenario import validate_live, validate_provisioning_endpoint
    validate_provisioning_endpoint(parent)
    context = ssl.create_default_context(cafile=str(Path(runtime) / 'proxmox-ca.pem'))
    def get(path):
        return request_json(parent['url'].rstrip('/') + '/api2/json/' + path,
                            'PVEAPIToken=' + parent['token'], context=context)['data']
    resources = get('cluster/resources?type=vm')
    owned_ids = {vm['vm_id'] for vm in plan['vms']}
    for resource in resources:
        resource['config'] = get(f"nodes/{resource['node']}/{resource['type']}/{resource['vmid']}/config")
        if int(resource['vmid']) in owned_ids:
            # The cluster summary is cached by pvestatd, including power state.
            resource['status'] = get(f"nodes/{resource['node']}/{resource['type']}/{resource['vmid']}/status/current")['status']
    validate_action(plan, resources, action, confirmation)
    vnets = get('cluster/sdn/vnets')
    subnets = [{**s, 'vnet': v['vnet']} for v in vnets for s in get(f"cluster/sdn/vnets/{v['vnet']}/subnets")]
    # Stop, backup and recovery remain available when an owned VM has NIC drift.
    validate_live(plan, resources, vnets, get('cluster/sdn/zones'), subnets,
                  require_owned_network=action == 'start')
    return {'vms': plan['vms'], 'subnets': [s['subnet'] for s in subnets if s['vnet'] == plan['bridge']],
            'vnet_exists': any(v['vnet'] == plan['bridge'] for v in vnets)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup-state', 'restore-state', 'rollback-state', 'authorize-upgrade', 'guard'])
    for name in ('instance', 'archive', 'plan', 'runtime', 'revisions'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--operation'); parser.add_argument('--confirm')
    args = parser.parse_args()
    if args.action == 'backup-state': backup_state(args.instance, args.archive)
    elif args.action == 'restore-state': restore_state(args.archive, args.instance)
    elif args.action == 'rollback-state': rollback_state(args.instance, args.archive)
    elif args.action == 'authorize-upgrade': authorize_upgrade(args.instance, json.loads(args.revisions.read_text()), args.archive)
    else: print(json.dumps(live_guard(json.loads(args.plan.read_text()), args.runtime, json.load(sys.stdin), args.operation, args.confirm)))


if __name__ == '__main__':
    main()
