import json
from pathlib import Path
import unittest
from range42_stack import plan
from test_plan import spec


class ProjectComponentTests(unittest.TestCase):
    def test_exports_a_self_contained_component_for_an_existing_project(self):
        self.assertTrue(callable(getattr(plan, 'project_component', None)), 'Stack needs a project component exporter')
        result = plan.project_component(spec(), Path(__file__).resolve().parents[2])
        files = result['files']
        path = result['scenario']['path']
        self.assertEqual(path, 'platforms/alpha')
        self.assertEqual(json.loads(files[path + '/manifest/stack.json'])['id'], 'alpha')
        runtime = json.loads(files[path + '/manifest/scenario_runtime.json'])
        self.assertEqual(runtime['bundle_path'], 'platform_runtime/bundles')
        self.assertIn('platform_runtime/range42_stack/scenario.py', files)
        self.assertIn('platform_runtime/bundles/admin/platform.prepare.instance/main.yml', files)
        self.assertLess(sum(len(value.encode()) for value in files.values()), 2 * 1024 * 1024)
        self.assertIn('alpha.setup.sh', '\n'.join(files))
        self.assertEqual(len(result['plan']['vms']), 11)
