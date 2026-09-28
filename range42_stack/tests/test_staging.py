import json
from pathlib import Path
import tempfile
import unittest

import yaml

from range42_stack.plan import build_plan
from range42_stack.stage import stage_instance
from test_plan import spec


class StagingTests(unittest.TestCase):
    def fixtures(self, root):
        paths = [root / x for x in ('sources', 'runtime', 'template', 'tls', 'staging')]
        for p in paths:
            p.mkdir(mode=0o700)
        sources, runtime, template, tls, staging = paths
        for name in ('range42-backend-api', 'range42-deployer-ui', 'range42-reporting-tool'):
            repo = sources / name
            repo.mkdir()
            (repo / '.range42-revision').write_text('a' * 40)
            (repo / 'source-sentinel').write_text(name)
        (sources / 'range42-backend-api/requirements.txt').write_text('ansible-core==2.19.1\n')
        (sources / 'range42-reporting-tool/deploy').mkdir()
        (sources / 'range42-reporting-tool/deploy/Caddyfile').write_text('{$DOMAIN} {\n\ttls {$TLS_CONFIG}\n}\n')
        (runtime / 'range42-catalog').mkdir()
        (runtime / 'range42-catalog/.range42-revision').write_text('b' * 40)
        (template / 'secrets').mkdir(mode=0o700)
        for name, data in [('stack.json', '{"stack_id":"alpha"}'), ('target.json', '{}'),
                           ('secrets/default_vault.yml', '$ANSIBLE_VAULT;1.1;AES256\nfixture'),
                           ('secrets/vault_pass.txt', 'fixture')]:
            path = template / name
            path.write_text(data)
            path.chmod(0o600)
        return paths

    def test_rerun_preserves_secrets_and_source_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self.fixtures(Path(temp))
            plan = build_plan(dict(spec(), profile='core'))
            stage_instance(plan, *paths, {})
            root = paths[-1] / 'alpha'
            first = (root / 'backend/private/credentials.json').read_bytes()
            stage_instance(plan, *paths, {})
            self.assertEqual(first, (root / 'backend/private/credentials.json').read_bytes())
            self.assertFalse((paths[0] / 'range42-reporting-tool/deploy/.env').exists())
            self.assertIn('tls {$TLS_CONFIG}', (paths[0] / 'range42-reporting-tool/deploy/Caddyfile').read_text())
            self.assertTrue((root / 'backend/source/range42-backend-api/source-sentinel').is_file())
            self.assertFalse((root / 'backend/compose.yml').exists())

    def test_disabled_service_is_not_prepared_or_routed(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self.fixtures(Path(temp))
            stage_instance(build_plan(dict(spec(), profile='core')), *paths, {'reporting': False})
            root = paths[-1] / 'alpha'
            self.assertFalse((root / 'reporting').exists())
            config = yaml.safe_load((root / 'gateway/kong.yml').read_text())
            self.assertNotIn('reporting', {s['name'] for s in config['services']})

    def test_release_change_is_refused_without_rotating_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self.fixtures(Path(temp))
            plan = build_plan(dict(spec(), profile='core'))
            stage_instance(plan, *paths, {})
            private = paths[-1] / 'alpha/backend/private/credentials.json'
            original = private.read_bytes()
            (paths[0] / 'range42-backend-api/.range42-revision').write_text('c' * 40)
            with self.assertRaisesRegex(ValueError, 'Release changed'):
                stage_instance(plan, *paths, {})
            self.assertEqual(private.read_bytes(), original)

    def test_staging_rejects_an_unknown_or_non_boolean_service_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self.fixtures(Path(temp))
            plan = build_plan(dict(spec(), profile='core'))
            for enabled in ({'ui': 'NO'}, {'unexpected': True}):
                with self.subTest(enabled=enabled), self.assertRaises(ValueError):
                    stage_instance(plan, *paths, enabled)

    def test_staging_cannot_follow_an_instance_directory_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = self.fixtures(Path(temp))
            elsewhere = Path(temp) / 'elsewhere'
            elsewhere.mkdir()
            (paths[-1] / 'alpha').symlink_to(elsewhere, target_is_directory=True)
            with self.assertRaises(ValueError):
                stage_instance(build_plan(dict(spec(), profile='core')), *paths, {})
            self.assertEqual(list(elsewhere.iterdir()), [])

    def test_restage_removes_obsolete_source_files_but_preserves_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=self.fixtures(Path(temp)); plan=build_plan(dict(spec(),profile='core'))
            stage_instance(plan,*paths,{})
            root=paths[-1]/'alpha'
            private=(root/'backend/private/credentials.json').read_bytes()
            (root/'backend/source/range42-backend-api/removed-in-new-release.py').write_text('obsolete')
            stage_instance(plan,*paths,{})
            self.assertFalse((root/'backend/source/range42-backend-api/removed-in-new-release.py').exists())
            self.assertEqual((root/'backend/private/credentials.json').read_bytes(),private)


if __name__ == "__main__":
    unittest.main()
