"""Build private delivery directories without installing or starting applications."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from .install import claim_node, prepare_node, private_write, validate_template


def stage_instance(plan, sources, runtime, template, tls, destination, enabled):
    services = {vm['service'] for vm in plan['vms']}
    if not isinstance(enabled, dict) or set(enabled) - services or any(type(v) is not bool for v in enabled.values()):
        raise ValueError('Service switches must map known services to booleans')
    sources, runtime, template, tls = map(Path, (sources, runtime, template, tls))
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError("Staging must not be a symlink")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.stat().st_mode & 0o077:
        raise ValueError("Keep persistent staging private (0700)")
    for public in (sources, runtime, template, tls):
        if destination.resolve().is_relative_to(public.resolve()) or public.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Staging and installation inputs must be separate directories")
    validate_template(template, plan['id'])
    active = [vm for vm in plan['vms'] if enabled.get(vm['service'], True)]
    routing_plan = {**plan, 'endpoints': {k: v for k, v in plan['endpoints'].items() if enabled.get(k, True)}}
    revisions = {str(repo.relative_to(base)): (repo / '.range42-revision').read_text().strip()
                 for base in (sources, runtime) for repo in base.iterdir()
                 if repo.is_dir() and (repo / '.range42-revision').is_file()}
    root = destination / plan['id']
    if root.is_symlink():
        raise ValueError('Instance staging must not be a symlink')
    root.mkdir(exist_ok=True, mode=0o700)
    release = root / 'release.json'
    if release.exists() and json.loads(release.read_text()) != revisions:
        raise ValueError('Release changed; use an explicit upgrade and preserve the existing private staging')
    private_write(release, json.dumps(revisions, sort_keys=True))
    def copy(source, dest):
        if dest.is_symlink():
            raise ValueError('Delivery input directories cannot be symlinks')
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git', '.env', '__pycache__', '*.pyc', 'node_modules', 'preview'))
    for vm in active:
        service = vm['service']
        target = root / service
        claim_node(plan, service, target)
        private_write(target / 'plan.json', json.dumps(plan))
        helper = target / 'helper/range42_stack'
        helper.mkdir(parents=True, exist_ok=True)
        for module in Path(__file__).parent.glob('*.py'):
            shutil.copyfile(module, helper / module.name)
        if service in {'backend', 'ui', 'reporting'}:
            repo = {'backend': 'range42-backend-api', 'ui': 'range42-deployer-ui',
                    'reporting': 'range42-reporting-tool'}[service]
            copy(sources / repo, target / 'source' / repo)
        elif service in {'gitea', 'registry', 'mattermost', 'rocketchat', 'nextcloud'}:
            payload = 'gitea-registry' if service == 'registry' else service
            copy(runtime / 'range42-catalog/03_container_layer/docker/admin' / payload, target / 'source')
        if service in {'backend', 'cli'}:
            copy(runtime, target / 'runtime')
            (target / 'runtime/bundle-runtime.json').unlink(missing_ok=True)
            copy(template, target / 'template')
            private_write(target / 'private/target.json', (template / 'target.json').read_text())
            if service == 'cli':
                shutil.copyfile(sources / 'range42-backend-api/requirements.txt', target / 'runtime/cli-requirements.txt')
        if service == 'gateway':
            copy(tls, target / 'tls')
        prepare_node(plan, service, target)
        if service == 'gateway':
            from .render import kong_config
            import yaml
            private_write(target / 'kong.yml', yaml.safe_dump(kong_config(routing_plan)), 0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'sources', 'runtime', 'template', 'tls', 'destination'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    stage_instance(json.loads(args.plan.read_text()), args.sources, args.runtime, args.template,
                   args.tls, args.destination, json.load(sys.stdin))


if __name__ == '__main__':
    main()
