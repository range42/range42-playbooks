"""Custom stacks share the allocation declarations used by native scenarios."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from range42_stack.plan import build_plan, project_component
from range42_stack import scenario
from test_plan import spec

ROOT = Path(__file__).resolve().parents[2]


class ScenarioAllocationTests(unittest.TestCase):
    def test_planning_rejects_the_existing_native_scenario_vmids(self):
        with self.assertRaisesRegex(ValueError, r'1190.*dev_deployer_ui_lab'):
            build_plan(dict(spec(), vmid_start=1190))

    def test_planning_rejects_a_dedicated_bridge_already_used_by_native_scenarios(self):
        with self.assertRaisesRegex(ValueError, 'net142'):
            build_plan(dict(spec(), bridge='net142'))

    def test_planning_rejects_reserved_subnet_even_without_an_address_in_the_overlap(self):
        with self.assertRaisesRegex(ValueError, '192.168.144.0/24'):
            build_plan(dict(spec(), subnet='192.168.144.224/27', gateway='192.168.144.225'))

    def test_template_selection_cannot_reuse_a_reserved_guest(self):
        with self.assertRaisesRegex(ValueError, r'1190.*dev_deployer_ui_lab'):
            build_plan(dict(spec(), template_vmid=1190))

    def test_shared_template_reference_and_unrelated_existing_conflicts_are_allowed(self):
        plan = build_plan(dict(spec(), template_vmid=9232))
        self.assertEqual(plan['vms'][0]['template_vmid'], 9232)

    def test_project_component_checks_its_operator_selected_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scenarios').mkdir()
            (root / 'scenarios/_reserved.json').write_text(json.dumps({'scenario': 'private_lab', 'vm_id': 31000}) + '\n')
            with self.assertRaisesRegex(ValueError, 'private_lab'):
                project_component(spec(), root)

    def test_stale_registry_cannot_hide_new_manifest_allocations_or_secondary_nics(self):
        for reservation in (
            {'vm_id': 31001},
            {'vm_id': 40000, 'nics': [{'bridge': 'r42alpha', 'ip': '10.90.0.10/24'}]},
            {'vm_id': 40000, 'nics': [{'bridge': 'other', 'ip': '10.81.0.99/24'}]},
        ):
            with self.subTest(reservation=reservation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = root / 'scenarios/new_lab/manifest'
                manifest.mkdir(parents=True)
                (root / 'scenarios/_reserved.json').write_text('{"scenario":"old_lab","vm_id":40001}\n')
                (manifest / 'scenario_vms.json').write_text(json.dumps({'vms': [reservation]}))
                with self.assertRaisesRegex(ValueError, 'new_lab'):
                    project_component(spec(), root)

    def test_unreadable_or_malformed_reservations_do_not_look_available(self):
        for content in (None, '', 'not json', '{"scenario":"broken","vm_id":true}',
                        '{"scenario":"broken","vm_id":40000,"nics":["bad"]}'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'scenarios').mkdir()
                if content is not None:
                    (root / 'scenarios/_reserved.json').write_text(content)
                with self.assertRaisesRegex(ValueError, 'reservation'):
                    project_component(spec(), root)

    def test_reservation_reader_rejects_linked_or_oversized_sources(self):
        for invalid in ('symlink', 'oversized'):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'scenarios').mkdir()
                path = root / 'scenarios/_reserved.json'
                if invalid == 'symlink':
                    (root / 'elsewhere').write_text('{"scenario":"private","vm_id":40000}\n')
                    path.symlink_to(root / 'elsewhere')
                else:
                    path.write_text(' ' * (2 * 1024 * 1024 + 1))
                with self.assertRaisesRegex(ValueError, 'reservation'):
                    project_component(spec(), root)

    def test_validation_does_not_reserve_or_rewrite_the_scenario_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scenarios').mkdir()
            path = root / 'scenarios/_reserved.json'
            original = '{"scenario":"existing","vm_id":40000}\n'
            path.write_text(original)
            result = project_component(spec(), root)
            self.assertEqual(result['plan']['vms'][0]['vm_id'], 31000)
            self.assertEqual(path.read_text(), original)
            self.assertEqual([p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()], ['scenarios/_reserved.json'])

    def test_runtime_preflight_rechecks_reserved_allocations_before_private_inputs(self):
        plan = build_plan(spec())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'runtime'
            (runtime / 'range42-playbooks/scenarios').mkdir(parents=True)
            (runtime / 'range42-playbooks/scenarios/_reserved.json').write_text(json.dumps({'scenario': 'new_lab', 'vm_id': 31000}) + '\n')
            with self.assertRaisesRegex(ValueError, 'new_lab'), patch('range42_stack.scenario.request_json') as request, \
                    patch('range42_stack.release.verify_release', side_effect=ValueError('Allocation was not checked before release inputs')):
                scenario.preflight(plan, runtime, root / 'sources', root / 'private', root / 'tls', {'node': 'pve', 'ssh_user': 'alice'})
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
