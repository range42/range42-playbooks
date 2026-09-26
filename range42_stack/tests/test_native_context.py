import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from range42_stack import install, scenario
from range42_stack.plan import build_plan
from test_plan import spec


def template_at(root):
    template = root / 'template'
    for directory in ('secrets', 'workload/templates'):
        (template / directory).mkdir(parents=True, mode=0o700)
    for name, value in {
        'cli.json': json.dumps({'scenario': 'smoke'}),
        'secrets/default_vault.yml': '$ANSIBLE_VAULT;fixture',
        'secrets/vault_pass.txt': 'fixture-password',
        'workload/main.yml': '- hosts: proxmox\n  tasks: []\n',
        'workload/hosts.yml': 'all:\n  children:\n    proxmox:\n      hosts:\n        pve:\n          ansible_host: pve.example.test\n',
        'workload/templates/ansible-inventory.j2': 'all: {}\n',
        'workload/templates/ssh-config.j2': 'Host pve\n  Hostname pve.example.test\n',
    }.items():
        install.private_write(template / name, value)
    return template


class NativeContextTests(unittest.TestCase):
    def test_cli_wrapper_forwards_arguments_and_selects_its_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = install.bootstrap_cli(build_plan(spec()), root / 'state', template_at(root), root / 'runtime')
            script = workspace / 'scenario/smoke.setup.sh'
            self.assertTrue(script.is_file(), 'Modern range42-context needs the scenario setup wrapper')
            (root / 'bin').mkdir()
            install.private_write(root / 'bin/ansible-playbook', '#!/bin/sh\nprintf "%s\\n" "$@"\n', 0o700)
            result = subprocess.run(['bash', str(script), '-e', 'value=two words'], env={**os.environ,
                'PATH': str(root / 'bin') + ':' + os.environ['PATH'],
                'RANGE42_ANSIBLE_ROLES__INVENTORY_DIR': str(workspace / 'inventory'),
                'RANGE42_VAULT_PASSWORD_FILE': str(workspace / 'secrets/vault_pass.txt')},
                capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines()[-2:], ['-e', 'value=two words'])
            self.assertIn(str(workspace / 'inventory/inventory_default.yml'), result.stdout)
            self.assertIn("export RANGE42_INFRASTRUCTURE_CODENAME='alpha'", (workspace / 'sourced_range42.sh').read_text())

    def test_backend_context_uses_private_state_and_does_not_write_to_runtime(self):
        self.assertTrue(hasattr(install, 'bootstrap_backend'), 'Child API needs a discoverable native context')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / 'runtime'
            (runtime / 'range42-playbooks/bundles').mkdir(parents=True)
            (runtime / 'range42').mkdir()
            (runtime / 'ansible.cfg').write_text('[defaults]\n')
            (runtime / 'proxmox-ca.pem').write_text('fixture-private-ca\n')
            before = sorted(p.relative_to(runtime) for p in runtime.rglob('*'))
            template = template_at(root)
            workspace = install.bootstrap_backend(build_plan(spec()), root / 'api-state', template, runtime)
            self.assertEqual(workspace, root / 'api-state/home/range42.config/alpha-smoke')
            self.assertTrue((workspace / 'scenario/smoke.setup.sh').is_file())
            self.assertTrue((root / 'api-state/home/range42/range42-playbooks/scenarios/smoke/main.yml').is_file(),
                            'The canonical CLI discovers scenarios below HOME/range42 before sourcing a context')
            trust = (workspace / 'ca-bundle.pem').read_text()
            self.assertIn('fixture-private-ca', trust)
            self.assertIn('-----BEGIN CERTIFICATE-----', trust)
            self.assertEqual(before, sorted(p.relative_to(runtime) for p in runtime.rglob('*')))
            (template / 'secrets/vault_pass.txt').write_text('rotated-template')
            install.bootstrap_backend(build_plan(spec()), root / 'api-state', template, runtime)
            self.assertEqual((workspace / 'secrets/vault_pass.txt').read_text(), 'fixture-password')

    def test_generated_scenario_has_native_wrappers_named_for_its_export_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'selected-name'
            scenario.export_scenario(build_plan(spec()), output)
            self.assertTrue((output / 'selected-name.setup.sh').is_file())
            self.assertTrue((output / 'selected-name.setup_vms_only.sh').is_file())
            self.assertTrue((output / 'selected-name.delete_all.sh').is_file())

    def test_preflight_rejects_the_obsolete_generated_only_context_runtime(self):
        self.assertTrue(hasattr(scenario, 'validate_context_runtime'))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / 'roles/deployer.bootstrap/files/range42-context.sh'
            script.parent.mkdir(parents=True)
            script.write_text('if [[ -f "$scenario_target/main.yml" ]]; then\n    _r42_run_concrete main.yml\nfi\n')
            with self.assertRaisesRegex(ValueError, 'native'):
                scenario.validate_context_runtime(root)
            script.write_text('_r42_deploy() { local setup_script="${scenario_target}/${scenario_name}.setup.sh"; }\n')
            scenario.validate_context_runtime(root)
