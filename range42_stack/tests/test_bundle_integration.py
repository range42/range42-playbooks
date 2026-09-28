"""Check generated imports against the real merged bundle interfaces."""
import json
from pathlib import Path
import unittest
import tempfile

import yaml
from jinja2 import Environment, StrictUndefined

from range42_stack.plan import build_plan
from range42_stack.scenario import render_scenario
from test_plan import spec

ROOT = Path(__file__).resolve().parents[2]


class BundleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.files = render_scenario(build_plan(spec()))

    def test_existing_application_installers_are_reused(self):
        for service, bundle in {
            'ui': 'deployer_ui', 'backend': 'deployer_api_backend', 'gateway': 'kong',
            'wazuh': 'wazuh', 'gitea': 'gitea', 'registry': 'gitea_registry',
            'mattermost': 'mattermost', 'rocketchat': 'rocketchat', 'nextcloud': 'nextcloud',
            'reporting': 'reporting', 'cli': 'deployer_cli',
        }.items():
            with self.subTest(service=service):
                plays = yaml.safe_load(self.files[f'nodes/{service}.yml'])
                imports = [p['import_playbook'] for p in plays if 'import_playbook' in p]
                self.assertTrue(any(f'/admin/software.install.{bundle}/main.yml' in p for p in imports), imports)
                self.assertFalse(any('tasks' in p or 'roles' in p for p in plays),
                                 'Scenario wrappers must compose bundles, not install applications')

    def test_vm_redeploy_keeps_configuration_and_firewall_stages(self):
        full = yaml.safe_load(self.files['main.yml'])
        fast = yaml.safe_load(self.files['main_vms_only.yml'])
        self.assertEqual(full, fast, 'Both entry points use a pre-existing template and must configure it')
        content = '\n'.join(self.files.values())
        for name in ('firewall.report.status', 'firewall.baseline.management_access',
                     'firewall.baseline.ssh_all_vms', 'firewall.enable.vms'):
            self.assertIn(f'/{name}/main.yml', content)
        self.assertIn('FIREWALL_ARM_VMS', content)

    def test_service_switches_are_exposed_to_the_existing_feature_ui(self):
        self.assertIn('manifest/feature_flags.yml', self.files)
        flags = yaml.safe_load(self.files['manifest/feature_flags.yml'])['features']
        self.assertEqual(len(flags), 11)
        text = '\n'.join(self.files.values())
        for flag in flags:
            self.assertIn('INSTALL_' + flag['id'], text)
            self.assertIs(flag['default'], True)

    def test_all_generated_bundle_arguments_have_declared_contracts(self):
        checked = 0
        for filename, content in self.files.items():
            if not filename.endswith('.yml'):
                continue
            doc = yaml.safe_load(content)
            if not isinstance(doc, list):
                continue
            for play in doc:
                path = play.get('import_playbook', '')
                if 'RANGE42_BUNDLE_DIR' not in path:
                    continue
                relative = path.split('}}/', 1)[1].removesuffix('/main.yml')
                contract = ROOT / 'bundles' / relative / 'bundle_parameters.src.yml'
                self.assertTrue(contract.is_file(), relative)
                annotation = yaml.safe_load(contract.read_text())
                names = {p['name'] for p in annotation['params']}
                self.assertFalse(set(play.get('vars', {})) - names, (filename, relative, play.get('vars')))
                checked += 1
        self.assertGreater(checked, 20)

    def test_allocation_does_not_promise_resources_the_bundle_does_not_set(self):
        plan = build_plan(spec())
        for vm in plan['vms']:
            self.assertNotIn('disk_gb', vm, 'The shared bootstrap inherits the source template disk')
        self.assertNotIn('global_vm_extra_config', '\n'.join(self.files.values()))
        self.assertNotIn('global_vm_disk', '\n'.join(self.files.values()))

    def test_preflight_rejects_a_runtime_without_the_required_bundle_contracts(self):
        from range42_stack import scenario
        self.assertTrue(hasattr(scenario, 'validate_bundle_contracts'))
        scenario.validate_bundle_contracts(build_plan(spec()), ROOT / 'bundles')
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(ValueError, 'bundle'):
            scenario.validate_bundle_contracts(build_plan(spec()), Path(temp))

    def test_provisioning_context_must_match_the_planned_node_and_ssh_user(self):
        from range42_stack import scenario
        self.assertTrue(hasattr(scenario, 'validate_provisioning_context'))
        plan = build_plan(spec())
        parent = {'node': 'pve', 'ssh_user': 'alice',
                  'url': 'https://fixture.invalid:8006', 'api_host': 'fixture.invalid:8006'}
        scenario.validate_provisioning_context(plan, parent)
        for context in ({'node': 'other', 'ssh_user': 'alice'}, {'node': 'pve', 'ssh_user': 'bob'}):
            with self.assertRaisesRegex(ValueError, 'node and cloud-init user'):
                scenario.validate_provisioning_context(plan, dict(parent, **context))

    def test_actual_preflight_bundle_supplies_the_active_provisioning_context(self):
        from range42_stack.scenario import validate_provisioning_context
        env = Environment(undefined=StrictUndefined)
        env.filters['to_json'] = json.dumps
        values = dict(BUNDLE_PROVISIONING_API_URL='https://fixture.invalid:8006',
                      proxmox_api_host='fixture.invalid:8006',
                      proxmox_api_user='fixture@pve', proxmox_api_token_id='fixture',
                      proxmox_api_token_secret='fixture', proxmox_node='pve',
                      default_admin_vm_ci_user='alice')
        from range42_stack.scenario import validate_provisioning_endpoint
        for bundle, index in [('platform.prepare.instance', 0), ('platform.lifecycle', 1)]:
            with self.subTest(bundle=bundle):
                plays = yaml.safe_load((ROOT / f'bundles/admin/{bundle}/main.yml').read_text())
                task = plays[0]['tasks'][index]
                stdin = task.get('args', task['ansible.builtin.command'])['stdin']
                parent = json.loads(env.from_string(stdin).render(values))
                self.assertEqual(parent.get('api_host'), 'fixture.invalid:8006')
                if bundle == 'platform.prepare.instance':
                    self.assertEqual(parent.get('node'), 'pve', 'Actual bundle must pass the active node')
                    self.assertEqual(parent.get('ssh_user'), 'alice')
                    validate_provisioning_context(build_plan(spec()), parent)
                validate_provisioning_endpoint(parent)
                parent['url'] = 'https://other.invalid:8006'
                with self.assertRaisesRegex(ValueError, 'endpoint'):
                    validate_provisioning_endpoint(parent)

    def test_preflight_requires_the_same_https_endpoint_as_the_controller(self):
        from range42_stack.scenario import preflight, validate_provisioning_context
        from unittest.mock import patch
        plan = build_plan(spec())
        for host, url in [('pve.example:8006', 'https://PVE.example:8006/'),
                          ('pve.example', 'https://pve.example:443'),
                          ('[2001:db8::1]:8006', 'https://[2001:db8::1]:8006')]:
            validate_provisioning_context(plan, dict(node='pve', ssh_user='alice', api_host=host, url=url))
        for host, url in [('pve.example:8006', 'https://other.example:8006'),
                          ('pve.example:8006', 'https://pve.example'),
                          ('pve.example:8006', 'http://pve.example:8006'),
                          ('pve.example:8006', 'https://user@pve.example:8006'),
                          ('pve.example:8006', 'https://pve.example:8006/api2/json'),
                          ('pve.example:8006', 'https://pve.example:8006?x=1'),
                          ('pve.example:8006', 'https://pve.example:8006#fragment'),
                          ('pve.example:8006', 'https://pve.example:bad'),
                          ('', 'https://pve.example:8006')]:
            with self.subTest(host=host, url=url), patch('range42_stack.scenario.request_json') as request:
                with self.assertRaisesRegex(ValueError, 'endpoint'):
                    preflight(plan, Path('/missing-runtime'), Path('/missing-sources'), Path('/missing-private'), Path('/missing-tls'),
                              dict(node='pve', ssh_user='alice', api_host=host, url=url))
                request.assert_not_called()

    def test_wazuh_agent_ports_survive_hypervisor_firewall_arming(self):
        calls = yaml.safe_load(self.files['nodes/wazuh.yml'])
        profile = next(p for p in calls if 'firewall.baseline.wazuh/' in p['import_playbook'])
        self.assertTrue({'443', '1514', '1515', '55000'} <= set(profile['vars']['BUNDLE_FW_PORTS']))

    def test_native_cli_connects_its_workspace_through_the_shared_ssh_role(self):
        plays = yaml.safe_load((ROOT / 'bundles/admin/software.install.deployer_cli/main.yml').read_text())
        includes = [t['ansible.builtin.include_role'] for p in plays for t in p.get('tasks', [])
                    if 'ansible.builtin.include_role' in t]
        self.assertIn({'name': 'workspace.ssh-config', 'tasks_from': '00_ensure_ssh_base.yml'}, includes)
        self.assertIn({'name': 'workspace.ssh-config', 'tasks_from': '02_inject_include_block.yml'}, includes)

    def test_existing_ui_deployments_keep_their_implicit_compose_project_name(self):
        plays = yaml.safe_load((ROOT / 'bundles/admin/software.install.deployer_ui/main.yml').read_text())
        content = next(t['ansible.builtin.copy']['content'] for p in plays for t in p.get('tasks', [])
                       if t.get('ansible.builtin.copy', {}).get('dest', '').endswith('/.env'))
        template = Environment(undefined=StrictUndefined).from_string(content)
        self.assertNotIn('COMPOSE_PROJECT_NAME=', template.render(UI_PORT_RESOLVED='3000'))
        self.assertIn('COMPOSE_PROJECT_NAME=r42-alpha-ui',
                      template.render(UI_PORT_RESOLVED='80', BUNDLE_COMPOSE_PROJECT='r42-alpha-ui'))


if __name__ == '__main__':
    unittest.main()

class RuntimeSelectionTests(unittest.TestCase):
    def test_saved_ui_checkout_can_use_identical_reviewed_bundles(self):
        from range42_stack import scenario
        self.assertTrue(hasattr(scenario, 'validate_runtime_selection'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('saved','release'):
                (root/name/'bundles').mkdir(parents=True)
                (root/name/'bundles/main.yml').write_text('reviewed')
                (root/name/'range42_stack').mkdir()
                (root/name/'range42_stack/install.py').write_text('reviewed helper')
            scenario.validate_runtime_selection(root/'saved/bundles', root/'release/bundles')
            (root/'saved/range42_stack/install.py').write_text('different helper')
            with self.assertRaisesRegex(ValueError, 'reviewed'):
                scenario.validate_runtime_selection(root/'saved/bundles', root/'release/bundles')

class ResumeTests(unittest.TestCase):
    def test_delivery_records_identity_before_a_transfer_can_be_interrupted(self):
        plays = yaml.safe_load((ROOT/'bundles/admin/platform.prepare.node/main.yml').read_text())
        tasks = plays[0]['tasks']
        transfer = next(i for i, t in enumerate(tasks) if 'ansible.posix.synchronize' in t)
        owner = [i for i, t in enumerate(tasks) if t.get('ansible.builtin.copy', {}).get('dest', '').endswith('/owner.json')]
        self.assertTrue(owner, 'A partial transfer needs an ownership marker to be resumable')
        self.assertLess(owner[0], transfer)

    def test_delivery_rsync_uses_the_same_jump_host_and_host_keys_as_ansible(self):
        for filename in ('admin/platform.prepare.node/main.yml', 'admin/software.install.deployer_ui/main.yml'):
            plays = yaml.safe_load((ROOT/'bundles'/filename).read_text())
            copies = [task['ansible.posix.synchronize'] for play in plays for task in play.get('tasks', [])
                      if 'ansible.posix.synchronize' in task]
            self.assertTrue(copies)
            for copy in copies:
                self.assertIs(copy.get('use_ssh_args'), True)
                self.assertIs(copy.get('verify_host'), True)

    def test_platform_bootstrap_requests_owned_vm_resume(self):
        files=render_scenario(build_plan(spec()))
        calls=yaml.safe_load(files['01_vm_bootstrap.yml'])
        self.assertTrue(all(p['vars'].get('BUNDLE_REUSE_OWNED_VM') for p in calls))
        plays=yaml.safe_load((ROOT/'bundles/proxmox/vm.bootstrap/main.yml').read_text())
        tasks=plays[0]['tasks']
        clone=next(t for t in tasks if t.get('vars',{}).get('proxmox_vm_action') == 'vm_clone')
        self.assertIn('vm_bootstrap_existing', str(clone.get('when','')))
        # Reapplying the shared cloud-init action stops the VM and regenerates
        # its MAC and instance identity. An explicitly resumed VM must skip it.
        from jinja2 import Environment
        environment = Environment(); environment.filters['bool'] = bool
        cloudinit = next(t for t in tasks if t.get('vars', {}).get('proxmox_vm_action') == 'cloudinit_set_variables')
        enabled = environment.compile_expression(cloudinit.get('when', 'true'))
        self.assertFalse(enabled(BUNDLE_REUSE_OWNED_VM=True, vm_bootstrap_existing={'status': 200}))
        self.assertTrue(enabled(BUNDLE_REUSE_OWNED_VM=True, vm_bootstrap_existing={'status': 500}))
        self.assertTrue(enabled())

class ControllerCompatibilityTests(unittest.TestCase):
    def test_release_rejects_a_controller_that_silently_skips_current_bundles(self):
        from range42_stack import scenario
        self.assertTrue(hasattr(scenario,'validate_controller_actions'))
        with tempfile.TemporaryDirectory() as temp:
            controller = Path(temp)
            tasks = controller/'roles/range42-ansible_roles-proxmox_controller/tasks'
            tasks.mkdir(parents=True)
            (tasks/'main.yml').write_text('- debug: msg=legacy-controller\n')
            with self.assertRaisesRegex(ValueError,'controller'):
                scenario.validate_controller_actions(controller)
