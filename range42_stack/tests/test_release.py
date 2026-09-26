import importlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class ReleaseTests(unittest.TestCase):
    def module(self):
        self.assertTrue((Path(__file__).parents[1] / 'release.py').is_file(), 'Release exporter is missing')
        return importlib.import_module('range42_stack.release')

    def repository(self, root):
        root.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
        git('init'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'fixture@example.test')
        (root / 'app.py').write_text('print("reviewed")\n')
        git('add', '.'); git('commit', '-m', 'fixture')
        return git('rev-parse', 'HEAD')

    def test_export_uses_exact_committed_content_and_detects_tampering(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); repo = root / 'repo'; sha = self.repository(repo)
            (repo / 'app.py').write_text('uncommitted')
            (repo / '.env').write_text('private')
            manifest = {'repositories': {'sources/app': {'path': str(repo), 'revision': sha}}}
            dest = root / 'release'
            module.export_release(manifest, dest)
            self.assertEqual((dest / 'sources/app/app.py').read_text(), 'print("reviewed")\n')
            self.assertFalse((dest / 'sources/app/.env').exists())
            module.verify_release(dest)
            (dest / 'sources/app/app.py').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                module.verify_release(dest)

    def test_export_refuses_floating_refs_and_existing_destination(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); sha = self.repository(root / 'repo')
            for ref in ('main', 'HEAD'):
                with self.assertRaises(ValueError):
                    module.export_release({'repositories': {'sources/app': {'path': str(root / 'repo'), 'revision': ref}}}, root / 'out')
            self.assertFalse((root / 'out').exists())
            with self.assertRaises(FileExistsError):
                module.export_release({'repositories': {'sources/app': {'path': str(root / 'repo'), 'revision': sha}}}, root)

    def test_lock_covers_runtime_assets_and_rejects_extra_files(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); sha = self.repository(root / 'repo')
            asset = root / 'ansible.cfg'; asset.write_text('[defaults]\n')
            module.export_release({'repositories': {'runtime/app': {'path': str(root / 'repo'), 'revision': sha}},
                                   'assets': {'runtime/ansible.cfg': str(asset)}}, root / 'out')
            module.verify_release(root / 'out')
            (root / 'out/runtime/extra').write_text('unexpected')
            with self.assertRaises(ValueError): module.verify_release(root / 'out')

    def test_python_import_caches_do_not_change_source_release_identity(self):
        module=self.module()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sha=self.repository(root/'repo')
            module.export_release({'repositories':{'runtime/app':{'path':str(root/'repo'),'revision':sha}}},root/'out')
            cache=root/'out/runtime/app/__pycache__';cache.mkdir();(cache/'app.cpython-312.pyc').write_bytes(b'cache')
            module.verify_release(root/'out')

    def test_required_collections_must_be_vendored_in_the_release(self):
        module=self.module();self.assertTrue(hasattr(module,'validate_collections'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaisesRegex(ValueError,'community.docker'):module.validate_collections(root)
            for name in ('community/docker','community/general','ansible/posix'):
                path=root/'ansible_collections'/name;path.mkdir(parents=True)
                (path/'MANIFEST.json').write_text(json.dumps({'collection_info':{'version':'1.0.0'}}))
            module.validate_collections(root)
