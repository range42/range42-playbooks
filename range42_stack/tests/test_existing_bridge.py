"""Borrow an operator network through the actual native stack workflow."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jinja2 import Environment, StrictUndefined
import yaml

from range42_stack import lifecycle, scenario
from range42_stack.plan import build_plan
from test_plan import spec


ROOT = Path(__file__).resolve().parents[2]


def borrowed_spec():
    return dict(spec(), profile='core', network_mode='existing_bridge', bridge='vmbr321')


def interface(**changes):
    return dict(iface='vmbr321', type='bridge', active=1, bridge_ports='none', **changes)


class ExistingBridgeTests(unittest.TestCase):
    def plan(self):
        try:
            return build_plan(borrowed_spec())
        except ValueError as error:
            self.fail('Native existing-bridge profile is missing: ' + str(error))

    def test_actual_cli_exports_borrowed_network_without_sdn_bootstrap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'spec.json').write_text(json.dumps(borrowed_spec()))
            result = subprocess.run([sys.executable, '-m', 'range42_stack', '--spec', str(root / 'spec.json'),
                                     '--output', str(root / 'scenario')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / 'scenario/manifest/scenario_networks.json').read_text())
            self.assertEqual(manifest, {'mode': 'existing_bridge', 'bridges': ['vmbr321']})
            self.assertFalse((root / 'scenario/00_sdn_bootstrap').exists())
            for filename in ['main.yml', 'main_vms_only.yml', 'configure.yml']:
                self.assertNotIn('sdn_network', (root / 'scenario' / filename).read_text())
            plan = json.loads((root / 'scenario/manifest/stack.json').read_text())
            self.assertEqual(plan['network_mode'], 'existing_bridge')
            self.assertNotIn('zone', plan)

    def test_unknown_modes_and_management_bridges_are_refused(self):
        for value in ['vmbr0', 'net142', 'vmbr321;echo', 'vmbr-321']:
            with self.subTest(bridge=value), self.assertRaises(ValueError):
                build_plan(dict(borrowed_spec(), bridge=value))
        with self.assertRaises(ValueError):
            build_plan(dict(borrowed_spec(), network_mode='automatic'))

    def test_borrowed_bridge_must_be_active_unaddressed_and_without_physical_ports(self):
        plan = self.plan()
        scenario.validate_live(plan, [], [], [], [], interfaces=[interface()])
        for changes in [{'active': 0}, {'type': 'OVSBridge'}, {'bridge_ports': 'eth0'},
                        {'address': '10.81.0.1'}, {'cidr': '10.81.0.1/24'},
                        {'address6': 'fd00::1'}, {'gateway': '10.81.0.1'}]:
            row = interface(); row.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                scenario.validate_live(plan, [], [], [], [], interfaces=[row])
        with self.assertRaises(ValueError):
            scenario.validate_live(plan, [], [], [], [], interfaces=[])

    def test_only_explicit_exact_operator_peers_can_share_the_borrowed_bridge(self):
        peer = {'vm_id': 40000, 'vm_name': 'operator-gateway', 'description': 'operator-network:fixture'}
        source = dict(borrowed_spec(), network_peers=[peer])
        try:
            plan = build_plan(source)
        except ValueError as error:
            self.fail('Missing explicit operator-peer binding: ' + str(error))
        live = {'vmid': 40000, 'name': 'operator-gateway', 'node': plan['node'], 'type': 'qemu',
                'config': {'description': peer['description'], 'net0': 'virtio=AA,bridge=vmbr321',
                           'net1': 'virtio=BB,bridge=vmbr0'}}
        scenario.validate_live(plan, [live], [], [], [], interfaces=[interface()])
        for change in [{'name': 'different'}, {'node': 'other'}, {'config': {'net0': 'virtio,bridge=vmbr321'}}]:
            changed = copy.deepcopy(live); changed.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                scenario.validate_live(plan, [changed], [], [], [], interfaces=[interface()])
        with self.assertRaises(ValueError):
            scenario.validate_live(plan, [], [], [], [], interfaces=[interface()])
        with self.assertRaises(ValueError):
            scenario.validate_live(self.plan(), [live], [], [], [], interfaces=[interface()])

    def test_operator_peer_cannot_overlap_owned_ids_or_be_implicitly_enabled_for_sdn(self):
        peer = {'vm_id': 31000, 'vm_name': 'operator-gateway', 'description': 'operator-network:fixture'}
        with self.assertRaises(ValueError):
            build_plan(dict(borrowed_spec(), network_peers=[peer]))
        peer['vm_id'] = 40000
        with self.assertRaises(ValueError):
            build_plan(dict(spec(), network_peers=[peer]))

    def test_duplicate_peer_bridge_fields_do_not_prove_attachment(self):
        peer = {'vm_id': 40000, 'vm_name': 'operator-gateway', 'description': 'operator-network:fixture'}
        try:
            plan = build_plan(dict(borrowed_spec(), network_peers=[peer]))
        except ValueError as error:
            self.fail(str(error))
        resource = {'vmid': 40000, 'name': peer['vm_name'], 'node': plan['node'],
                    'config': {'description': peer['description'],
                               'net0': 'virtio=AA,bridge=vmbr321,bridge=vmbr0'}}
        with self.assertRaises(ValueError):
            scenario.validate_live(plan, [resource], [], [], [], interfaces=[interface()])

    def test_borrowed_profile_does_not_require_an_sdn_bundle_in_the_runtime(self):
        plan = self.plan()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = scenario.render_scenario(plan)
            for content in files.values():
                for call in yaml.safe_load(content) if content.startswith('- ') else []:
                    bundle = call.get('import_playbook', '')
                    if 'RANGE42_BUNDLE_DIR' not in bundle:
                        continue
                    relative = bundle.split('}}/', 1)[1].removesuffix('/main.yml')
                    target = root / relative
                    target.mkdir(parents=True, exist_ok=True)
                    (target / 'main.yml').write_text('[]\n')
                    (target / 'bundle_parameters.src.yml').write_text(yaml.safe_dump({
                        'params': [{'name': name} for name in call.get('vars', {})]}))
            scenario.validate_bundle_contracts(plan, root)
            self.assertFalse((root / 'proxmox/sdn_network.bootstrap').exists())

    def test_lifecycle_reads_only_borrowed_bridge_and_keeps_network_outside_its_scope(self):
        plan = self.plan()
        resources = [{'vmid': vm['vm_id'], 'name': vm['vm_name'], 'node': plan['node'], 'type': 'qemu'}
                     for vm in plan['vms']]
        calls = []

        def api(url, token, **kwargs):
            path = url.split('/api2/json/')[1]
            calls.append(path)
            if path == 'cluster/resources?type=vm':
                return {'data': copy.deepcopy(resources)}
            if path == 'nodes/pve/network':
                return {'data': [interface()]}
            if path.endswith('/config'):
                return {'data': {'description': 'range42-stack:alpha', 'net0': 'virtio=AA,bridge=vmbr321'}}
            if path.endswith('/status/current'):
                return {'data': {'status': 'running'}}
            self.fail('Unexpected infrastructure request: ' + path)

        parent = {'url': 'https://fixture.invalid:8006', 'api_host': 'fixture.invalid:8006', 'token': 'fixture'}
        with patch.object(lifecycle, 'request_json', api), patch.object(lifecycle.ssl, 'create_default_context'):
            result = lifecycle.live_guard(plan, Path('/unused'), parent, 'start', 'alpha')
        self.assertFalse(result['vnet_exists'])
        self.assertEqual(result['subnets'], [])
        self.assertEqual(result['network_mode'], 'existing_bridge')
        self.assertIn('nodes/pve/network', calls)
        self.assertFalse(any('sdn' in path for path in calls))

    def test_real_lifecycle_conditions_select_no_network_mutation_for_borrowed_mode(self):
        plays = yaml.safe_load((ROOT / 'bundles/admin/platform.lifecycle/main.yml').read_text())
        candidates = [p for p in plays if 'sdn_network' in p.get('import_playbook', '')]
        tasks = [t for p in plays for t in p.get('tasks', []) if t.get('ansible.builtin.include_tasks') == 'network.yml']
        env = Environment(undefined=StrictUndefined)
        for action in ['restore', 'teardown']:
            scope = {'network_mode': 'existing_bridge', 'vnet_exists': True}
            context = {'BUNDLE_ACTION': action, 'platform_scope': scope}
            for operation in [*candidates, *tasks]:
                selected = env.compile_expression(operation['when'])(**context)
                self.assertFalse(selected, (action, operation))
        # Legacy/SDN mode retains its actual restore and teardown paths.
        for action in ['restore', 'teardown']:
            context = {'BUNDLE_ACTION': action, 'platform_scope': {'network_mode': 'sdn', 'vnet_exists': True}}
            self.assertTrue(any(env.compile_expression(p['when'])(**context) for p in candidates))
