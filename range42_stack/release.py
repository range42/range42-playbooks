"""Export exact Git revisions and verify the complete deployable release.

python3 -m range42_stack.release export --manifest release-input.json --directory /private/release
python3 -m range42_stack.release verify --directory /private/release

Input: repositories maps sources/<repo> or runtime/<repo> to {path, revision}.
Assets maps runtime/ansible.cfg, runtime/collections, runtime/proxmox-ca.pem to local paths.
The release lock records every byte, including vendored collections; private credentials stay separate.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile


def relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {'', '.', '..'} for part in name.split('/')) or '\\' in name:
        raise ValueError('Release paths must stay inside the export')
    if path.parts[0] not in {'sources', 'runtime'}:
        raise ValueError('Release entries must belong to sources or runtime')
    return path


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if name == 'release.lock.json' or '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'}:
            continue
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()) or not path.exists():
                raise ValueError('Release contains an escaping or broken symlink')
            result[name] = {'link': str(path.readlink())}
        elif path.is_file():
            if path.name == '.env' or '.git' in path.parts or 'secrets' in path.relative_to(root).parts:
                raise ValueError('Release must not contain private environment or credential files')
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            result[name] = {'sha256': digest,
                            'executable': bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise ValueError('Release contains a special file')
    return result


def verify_release(root):
    root = Path(root)
    lock = json.loads((root / 'release.lock.json').read_text())
    if lock.get('version') != 1 or inventory(root) != lock.get('files'):
        raise ValueError('Release integrity check failed')
    return lock


def validate_collections(root):
    """Do not silently resolve required modules from the controller's global install."""
    required = ['community.docker', 'community.general', 'ansible.posix']
    seen = set()
    while required:
        name = required.pop(0)
        if name in seen:
            continue
        seen.add(name)
        try:
            info = json.loads((Path(root) / 'ansible_collections' / name.replace('.', '/') / 'MANIFEST.json').read_text())['collection_info']
            if not info.get('version'):
                raise ValueError()
            required.extend(info.get('dependencies', {}))
        except (OSError, ValueError, KeyError):
            raise ValueError('Release is missing required collection ' + name) from None


def export_release(manifest, destination):
    destination = Path(destination)
    repos = manifest.get('repositories', {})
    if not repos:
        raise ValueError('A release needs reviewed repository revisions')
    for name, repo in repos.items():
        relative(name)
        if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', repo['revision']):
            raise ValueError('Use exact Git commit revisions, not floating refs')
        actual = subprocess.check_output(['git', '-C', repo['path'], 'rev-parse', repo['revision'] + '^{commit}'],
                                         stderr=subprocess.DEVNULL).decode().strip()
        if actual != repo['revision']:
            raise ValueError('Release revision must identify a commit')
    for name in manifest.get('assets', {}):
        relative(name)
        if any(name == repo or name.startswith(repo + '/') for repo in repos):
            raise ValueError('Runtime assets cannot replace repository files')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.range42-release-') as temp:
        root = Path(temp)
        for name, repo in repos.items():
            data = subprocess.check_output(['git', '-C', repo['path'], 'archive', '--format=tar', repo['revision']])
            target = root / name
            target.mkdir(parents=True)
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                archive.extractall(target, filter='data')
            (target / '.range42-revision').write_text(repo['revision'] + '\n')
        for name, source in manifest.get('assets', {}).items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if Path(source).is_dir():
                shutil.copytree(source, target, symlinks=True)
            else:
                shutil.copy2(source, target)
        lock = {'version': 1, 'repositories': {name: repo['revision'] for name, repo in repos.items()},
                'files': inventory(root)}
        (root / 'release.lock.json').write_text(json.dumps(lock, sort_keys=True, indent=2) + '\n')
        root.rename(destination)
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['export', 'verify'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    if args.action == 'export':
        if not args.manifest:
            parser.error('export requires --manifest')
        result = export_release(json.loads(args.manifest.read_text()), args.directory)
    else:
        result = verify_release(args.directory)
    print(json.dumps({'verified': True, 'repositories': result['repositories'], 'files': len(result['files'])}))


if __name__ == '__main__':
    main()
