"""The reservation checker must inspect every NIC and tolerate template ID references."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReservationTests(unittest.TestCase):
    def check(self, scenarios):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('_check_reserved.sh', '_regenerate_reserved.sh'):
                shutil.copyfile(ROOT / 'scenarios' / name, root / name)
            for name, document in scenarios.items():
                directory = root / name / 'manifest'
                directory.mkdir(parents=True)
                (directory / 'scenario_vms.json').write_text(json.dumps(document))
            subprocess.run(['bash', str(root / '_regenerate_reserved.sh')], check=True, capture_output=True)
            return subprocess.run(['bash', str(root / '_check_reserved.sh')], text=True, capture_output=True)

    def scenario(self, vm_id=3191):
        return {'version': 3, 'vms': [{'vm_id': vm_id, 'vm_name': f'vm-{vm_id}', 'bridge': 'net1', 'ip': '10.1.0.10',
                'nics': [{'index': 0, 'bridge': 'net1', 'ip': '10.1.0.10'}, {'index': 1, 'bridge': 'net2', 'ip': '10.2.0.10'}]}], 'templates': []}

    def test_secondary_nic_collides_with_legacy_primary_nic(self):
        other = {'vms': [{'vm_id': 3192, 'vm_name': 'other', 'bridge': 'net2', 'ip': '10.2.0.10'}], 'templates': []}
        result = self.check({'multi': self.scenario(), 'legacy': other})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('net2 10.2.0.10', result.stdout)

    def test_secondary_nic_collides_with_template_address(self):
        scenario = self.scenario()
        scenario['templates'] = [{'vm_id': 9901, 'vm_name': 'template', 'bridge': 'net2', 'ip': '10.2.0.10'}]
        result = self.check({'multi': scenario})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cross-role', result.stdout)

    def test_distinct_template_id_only_references_have_no_phantom_ip_collision(self):
        scenario = self.scenario()
        scenario['templates'] = [{'vm_id': 9901}, {'vm_id': 9902}]
        result = self.check({'multi': scenario})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_template_id_reference_does_not_conflict_with_full_template_definition(self):
        scenario = self.scenario()
        scenario['templates'] = [{'vm_id': 9901}]
        other = {'vms': [], 'templates': [{'vm_id': 9901, 'vm_name': 'base', 'spec': 'ubuntu', 'bridge': 'vmbr0', 'ip': '192.0.2.10'}]}
        result = self.check({'multi': scenario, 'template': other})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_same_ip_on_a_different_bridge_is_not_a_collision(self):
        other = {'vms': [{'vm_id': 3192, 'vm_name': 'other', 'bridge': 'net3', 'ip': '10.2.0.10'}], 'templates': []}
        result = self.check({'multi': self.scenario(), 'legacy': other})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
