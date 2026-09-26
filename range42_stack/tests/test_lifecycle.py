import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from range42_stack.plan import build_plan
from test_plan import spec


class LifecycleTests(unittest.TestCase):
    def module(self):
        self.assertTrue((Path(__file__).parents[1] / 'lifecycle.py').is_file(), 'Lifecycle helpers are missing')
        return importlib.import_module('range42_stack.lifecycle')

    def test_backup_restore_preserves_credentials_and_refuses_overwrite(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); instance = root / 'stage/alpha'; instance.mkdir(parents=True)
            (instance / 'release.json').write_text('{"app":"old"}')
            (instance / 'backend/private').mkdir(parents=True)
            secret = instance / 'backend/private/key'; secret.write_text('original-key'); secret.chmod(0o600)
            script = instance / 'backend/start.sh'; script.write_text('#!/bin/sh\nexit 0\n'); script.chmod(0o755)
            archive = root / 'backup.tar.gz'
            module.backup_state(instance, archive)
            module.restore_state(archive, root / 'restored/alpha')
            self.assertEqual((root / 'restored/alpha/backend/private/key').read_text(), 'original-key')
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / 'restored/alpha/backend/start.sh').stat().st_mode & 0o777, 0o700)
            with self.assertRaises(FileExistsError): module.restore_state(archive, instance)
            with self.assertRaises(FileExistsError): module.backup_state(instance, archive)

    def test_destructive_guard_requires_every_vm_to_be_owned_and_stopped(self):
        module = self.module(); plan = build_plan(dict(spec(), profile='core'))
        resources = [dict(vmid=v['vm_id'], name=v['vm_name'], node=plan['node'], status='stopped',
                          config={'description': 'range42-stack:alpha'}) for v in plan['vms']]
        module.validate_action(plan, resources, 'teardown', 'alpha')
        with self.assertRaises(ValueError): module.validate_action(plan, resources, 'teardown', 'bravo')
        resources[0]['status'] = 'running'
        with self.assertRaisesRegex(ValueError, 'stopped'): module.validate_action(plan, resources, 'teardown', 'alpha')
        resources[0]['status'] = 'stopped'; resources[0]['config']['description'] = 'foreign'
        with self.assertRaisesRegex(ValueError, 'ownership'): module.validate_action(plan, resources, 'rollback', 'alpha')

    def test_live_guard_uses_current_power_state_instead_of_the_cluster_cache(self):
        module = self.module(); plan = build_plan(dict(spec(), profile='core'))
        for cached, current in [('running', 'stopped'), ('stopped', 'running')]:
            def request(url, *args, **kwargs):
                path = url.split('/api2/json/')[1]
                if path == 'cluster/resources?type=vm':
                    value = [dict(vmid=v['vm_id'], name=v['vm_name'], node=plan['node'],
                                  type='qemu', status=cached) for v in plan['vms']]
                elif path.endswith('/config'):
                    value = {'description': 'range42-stack:alpha'}
                elif path.endswith('/status/current'):
                    value = {'status': current}
                else:
                    value = []
                return {'data': value}
            with patch.object(module, 'request_json', side_effect=request), \
                    patch.object(module.ssl, 'create_default_context'):
                args = (plan, '/runtime', {'url': 'https://pve', 'token': 'fixture'}, 'checkpoint', 'alpha')
                if current == 'stopped':
                    try:
                        result = module.live_guard(*args)
                    except ValueError as error:
                        self.fail('The stale cluster summary overrode current VM state: ' + str(error))
                    self.assertEqual(len(result['vms']), 5)
                else:
                    with self.assertRaisesRegex(ValueError, 'stopped'):
                        module.live_guard(*args)

    def test_state_restore_rejects_traversal_and_links(self):
        import io, tarfile
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('../escape', '/absolute'):
                archive = root / 'bad.tar'
                with tarfile.open(archive, 'w') as tar:
                    info = tarfile.TarInfo(name); info.size = 1; tar.addfile(info, io.BytesIO(b'x'))
                with self.assertRaises(ValueError): module.restore_state(archive, root / 'restored')
                self.assertFalse((root / 'restored').exists())

    def test_upgrade_requires_a_matching_backup_and_keeps_private_keys(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); instance=root/'alpha'; instance.mkdir()
            (instance/'release.json').write_text('{"app":"old"}')
            (instance/'key').write_text('private')
            module.backup_state(instance, root/'backup.tar.gz')
            module.authorize_upgrade(instance, {'app':'new'}, root/'backup.tar.gz')
            self.assertEqual(json.loads((instance/'release.json').read_text()), {'app':'new'})
            self.assertEqual((instance/'key').read_text(), 'private')
            with self.assertRaises(ValueError): module.authorize_upgrade(instance, {'app':'another'}, root/'backup.tar.gz')

    def test_native_actions_reuse_the_shared_lifecycle_bundle(self):
        from range42_stack.scenario import render_scenario
        import yaml
        files = render_scenario(build_plan(dict(spec(), profile='core')))
        for action in ('stop', 'start', 'checkpoint', 'backup', 'restore', 'rollback', 'teardown'):
            self.assertIn(action + '.yml', list(files))
            calls = yaml.safe_load(files[action + '.yml'])
            self.assertIn('/admin/platform.lifecycle/', calls[0]['import_playbook'])
            self.assertEqual(calls[0]['vars']['BUNDLE_ACTION'], action)

    def test_rollback_restores_previous_release_and_retains_failed_state(self):
        module=self.module()
        self.assertTrue(hasattr(module,'rollback_state'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);instance=root/'alpha';instance.mkdir()
            (instance/'release.json').write_text('{"app":"old"}')
            (instance/'key').write_text('old-key')
            module.backup_state(instance,root/'state.tar.gz')
            (instance/'release.json').write_text('{"app":"new"}')
            previous=module.rollback_state(instance,root/'state.tar.gz')
            self.assertEqual(json.loads((instance/'release.json').read_text()),{'app':'old'})
            self.assertEqual(json.loads((previous/'release.json').read_text()),{'app':'new'})

    def test_lifecycle_finishes_network_removal_and_recreates_network_for_restore(self):
        import yaml
        root = Path(__file__).parents[2] / 'bundles/admin/platform.lifecycle'
        plays = yaml.safe_load((root / 'main.yml').read_text())
        imports = [p.get('import_playbook', '') for p in plays]
        self.assertTrue(any('sdn_network.apply/' in p for p in imports))
        self.assertTrue(any('sdn_network.reconcile.snat_rules/' in p for p in imports))
        self.assertTrue(any('sdn_network.bootstrap/' in p for p in imports))
        tasks = yaml.safe_load((root / 'backup.yml').read_text())
        self.assertTrue(any('ansible.builtin.copy' in t and '.vma.zst' in str(t) for t in tasks),
                        'Restoring must work from the controller backup when the PVE copy is gone')

    def test_start_waits_for_the_shared_guest_connection_check(self):
        import yaml
        plays = yaml.safe_load((Path(__file__).parents[2] / 'bundles/admin/platform.lifecycle/main.yml').read_text())
        startup = [p for p in plays if p.get('hosts') == 'platform']
        self.assertEqual(len(startup), 1, 'start.yml must wait for guest SSH before returning')
        play = startup[0]
        self.assertFalse(play['gather_facts'])
        self.assertIn('wait/openssh_server/is_reachable.yml', play['vars']['requested_tasks'])
        self.assertEqual(play['tasks'][0]['when'], "BUNDLE_ACTION == 'start'")
        self.assertEqual(play['tasks'][0]['ansible.builtin.include_role']['name'], 'ansible.utils')
