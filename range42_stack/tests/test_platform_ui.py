import json
import unittest
from range42_stack.plan import build_plan
from range42_stack.scenario import render_scenario
from test_plan import spec


class PlatformUiTests(unittest.TestCase):
    def test_native_descriptor_exposes_setup_presets_and_unavailable_components(self):
        files = render_scenario(build_plan(spec()))
        self.assertIn('manifest/platform.json', files)
        ui = json.loads(files['manifest/platform.json'])
        presets = {p['id']: p['features'] for p in ui['presets']}
        self.assertEqual(sum(presets['core'].values()), 5)
        self.assertEqual(sum(presets['full'].values()), 11)
        self.assertEqual(set(ui['unavailable']), {'emp', 'misp'})
        fields = {p['name'] for p in ui['parameters']}
        self.assertIn('stack_tls_dir', fields)
        self.assertIn('stack_management_cidrs', fields)
        self.assertFalse(any('token' in p or 'password' in p for p in fields))
