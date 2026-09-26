import importlib
from pathlib import Path
import tempfile
import unittest

import yaml

from range42_stack.plan import build_plan
from test_plan import spec


class SourceReuseTests(unittest.TestCase):
    def test_backend_uses_the_application_compose_files(self):
        module = importlib.import_module('range42_stack.install')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'source/range42-backend-api').mkdir(parents=True)
            for name in ('docker-compose.yml', 'docker-compose.runtime.yml'):
                (root / 'source/range42-backend-api' / name).write_text('services: {api: {image: upstream-sentinel}}\n')
            template = root / 'template'
            (template / 'secrets').mkdir(parents=True, mode=0o700)
            template.chmod(0o700)
            for name, content in [('stack.json', '{"stack_id":"alpha"}'),
                                  ('secrets/default_vault.yml', '$ANSIBLE_VAULT;1.1;AES256\nfixture'),
                                  ('secrets/vault_pass.txt', 'fixture')]:
                path = template / name
                path.write_text(content)
                path.chmod(0o600)
            module.prepare_node(build_plan(spec()), 'backend', root)
            self.assertFalse((root / 'compose.yml').exists(), 'Do not maintain a second backend Compose graph')
            self.assertTrue((root / 'private/backend.env').is_file())
            self.assertIn('upstream-sentinel', (root / 'source/range42-backend-api/docker-compose.yml').read_text())

    def test_reporting_overrides_only_instance_configuration(self):
        from range42_stack.install import prepare_node
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'source/range42-reporting-tool/deploy').mkdir(parents=True)
            prepare_node(build_plan(spec()), 'reporting', root)
            self.assertFalse((root / 'compose.yml').exists(), 'Use reporting-tool/deploy Compose files')
            self.assertTrue((root / 'reporting.override.yml').is_file())
            text = (root / 'reporting.override.yml').read_text()
            self.assertNotIn('image:', text)
            self.assertNotIn('build:', text)
            self.assertIn('POSTGRES_PASSWORD', text)

    def test_wazuh_has_private_vars_for_the_shared_installer(self):
        from range42_stack.install import prepare_node
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prepare_node(build_plan(spec()), 'wazuh', root)
            path = root / 'private/wazuh.yml'
            self.assertTrue(path.is_file())
            data = yaml.safe_load(path.read_text())
            self.assertTrue(data['infrastructure_wazuh_admin_password'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
