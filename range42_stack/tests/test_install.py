import importlib
import json
from pathlib import Path
import tempfile
import unittest
import ssl
import shutil
from unittest.mock import patch

from range42_stack.plan import build_plan
from test_plan import spec


class InstallTests(unittest.TestCase):
    def installer(self):
        self.assertTrue((Path(__file__).parents[1] / "install.py").exists(), "isolated node installer is missing")
        return importlib.import_module("range42_stack.install")

    def test_credential_template_requires_matching_owner_and_no_symlinks(self):
        module = self.installer()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.chmod(0o700)
            (root / "secrets").mkdir(mode=0o700)
            for name, data in [("stack.json", json.dumps({"stack_id": "alpha"})),
                               ("secrets/default_vault.yml", "$ANSIBLE_VAULT;1.1;AES256\ntest"),
                               ("secrets/vault_pass.txt", "test-password")]:
                path = root / name
                path.write_text(data)
                path.chmod(0o600)
            module.validate_template(root, "alpha")
            with self.assertRaises(ValueError):
                module.validate_template(root, "bravo")
            (root / "secrets/vault_pass.txt").chmod(0o644)
            with self.assertRaises(ValueError):
                module.validate_template(root, "alpha")
            (root / "secrets/vault_pass.txt").unlink()
            (root / "secrets/vault_pass.txt").symlink_to(root / "stack.json")
            with self.assertRaises(ValueError):
                module.validate_template(root, "alpha")

    def test_catalog_environment_generates_unique_admins_without_demo_users(self):
        module = self.installer()
        from range42_stack.render import ensure_credentials
        with tempfile.TemporaryDirectory() as temp:
            credentials = ensure_credentials(Path(temp) / "private", "alpha", "gitea")
            env = module.catalog_environment(build_plan(spec()), "gitea", credentials)
            self.assertEqual(env["GITEA_BASE_URL"], "https://gitea.alpha.example.test")
            self.assertEqual(env["POSTGRES_PASSWORD"], credentials["database_password"])
            users = module.catalog_users(build_plan(spec()), "gitea", credentials)
            self.assertEqual(users["users"], [])
            self.assertEqual(len(users["admins"]), 1)
            self.assertEqual(users["admins"][0]["password"], credentials["admin_password"])

    def test_node_render_does_not_write_outside_owned_root(self):
        module = self.installer()
        plan = build_plan(spec())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ui"
            module.prepare_node(plan, "ui", root)
            first = (root / "private/credentials.json").read_text()
            self.assertEqual(json.loads((root / "config.json").read_text())["defaultBackendUrl"],
                             "https://api.alpha.example.test")
            module.prepare_node(plan, "ui", root)
            self.assertEqual(first, (root / "private/credentials.json").read_text())
            with self.assertRaises(ValueError):
                module.prepare_node(build_plan(spec("bravo", 32000, "10.82.0.0/24", "r42bravo")), "ui", root)
            self.assertEqual(set(Path(temp).iterdir()), {root})

    def test_rejects_overprivileged_or_unrelated_target_access(self):
        module = self.installer()
        module.validate_target_permissions({"/pool/r42-alpha": {"VM.Allocate": 1},
                                            "/storage/local-lvm": {"Datastore.AllocateSpace": 1}},
                                           ["/pool/r42-alpha", "/storage/local-lvm"])
        for permissions in [{"/": {"VM.Allocate": 1}}, {"/pool/r42-bravo": {"VM.PowerMgmt": 1}},
                            {"/pool/r42-alpha": {"Permissions.Modify": 1}}]:
            with self.assertRaises(ValueError):
                module.validate_target_permissions(permissions, ["/pool/r42-alpha"])

    def test_backend_preparation_refuses_an_absent_dedicated_template(self):
        module = self.installer()
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            module.prepare_node(build_plan(spec()), "backend", Path(temp) / "backend")

    def test_cli_has_a_usable_private_context_and_preserves_existing_credentials(self):
        module = self.installer()
        self.assertTrue(hasattr(module, "bootstrap_cli"), "CLI workspace bootstrap is missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "template"
            (template / "secrets").mkdir(parents=True, mode=0o700)
            (template / "secrets/default_vault.yml").write_text("original-vault")
            (template / "secrets/vault_pass.txt").write_text("original-password")
            workload = template / 'workload'
            (workload / 'templates').mkdir(parents=True)
            (template / 'cli.json').write_text(json.dumps({'scenario': 'smoke'}))
            (workload / 'hosts.yml').write_text('all:\n  hosts:\n    smoke:\n      ansible_host: 10.81.0.90\n')
            (workload / 'main.yml').write_text('- hosts: all\n  tasks:\n  - ansible.builtin.ping:\n')
            (workload / 'templates/ansible-inventory.j2').write_text((workload / 'hosts.yml').read_text())
            (workload / 'templates/ssh-config.j2').write_text('Host smoke\n  Hostname 10.81.0.90\n')
            workspace = module.bootstrap_cli(build_plan(spec()), root / "state", template, root / "runtime")
            self.assertEqual(workspace.name, 'alpha-smoke')
            self.assertIn('smoke:', (workspace / 'inventory/inventory_default.yml').read_text())
            self.assertTrue((workspace / 'scenario/main.yml').is_file())
            self.assertIn('ANSIBLE_ROLES_PATH', (workspace / 'sourced_range42.sh').read_text())
            self.assertIn('/venv/bin', (workspace / 'sourced_range42.sh').read_text())
            self.assertTrue((workspace / "sourced_range42.sh").exists())
            self.assertTrue((root / "state/home/.ssh/config").exists())
            self.assertIn(str(workspace), (root / "state/home/.zshrc").read_text())
            (template / "secrets/vault_pass.txt").write_text("changed-password")
            module.bootstrap_cli(build_plan(spec()), root / "state", template, root / "runtime")
            self.assertEqual((workspace / "secrets/vault_pass.txt").read_text(), "original-password")

    def test_cli_refuses_to_claim_ready_without_a_workload_scenario(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'template').mkdir()
            with self.assertRaisesRegex(ValueError, 'workload'):
                self.installer().bootstrap_cli(build_plan(spec()), root / 'state', root / 'template', root / 'runtime')

    def test_default_catalog_registration_uses_the_backends_canonical_branches(self):
        module = self.installer()
        requests = []
        def http(url, token, body=None, context=None):
            requests.append((url, token, body))
            if url.endswith("/access/permissions"):
                return {"data": {"/pool/r42-alpha": {"VM.Allocate": 1}}}
            if "/catalog/sources?" in url:
                return {"items": [], "total": 0, "offset": 0, "limit": 100}
            if url.endswith("/health/ready"):
                return {"ready": True, "checks": {}, "timestamp": "2026-09-24T00:00:00Z"}
            if url.endswith('/contexts'):
                return {'items': [{'id': 'alpha-smoke', 'ready': True}]}
            return {}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "private").mkdir()
            (root / "runtime").mkdir()
            shutil.copyfile(ssl.get_default_verify_paths().cafile, root / "runtime/proxmox-ca.pem")
            (root / "private/api-token").write_text("fixture-api-token")
            (root / 'template').mkdir()
            (root / 'template/cli.json').write_text('{"scenario":"smoke"}')
            (root / "private/target.json").write_text(json.dumps({"host": {"name": "alpha",
                "node_name": "pve", "default_bridge": "r42alpha", "api_url": "https://pve.example.test:8006",
                "token_ref": "fixture-child-token"}, "allowed_paths": ["/pool/r42-alpha"]}))
            with patch.object(module, "request_json", side_effect=http):
                try:
                    module.seed_backend(build_plan(spec()), root)
                except FileNotFoundError as error:
                    self.fail(f"Catalog onboarding must use server defaults, not treat an export SHA as a branch: {error}")
            self.assertEqual({url.rsplit("kind=", 1)[-1] for url, _, _ in requests if "/sources/default?" in url},
                             {"catalog", "bundles"})
            self.assertTrue(any(url.endswith('/contexts') for url, _, _ in requests))
            self.assertTrue(all(token == "Bearer fixture-api-token" for url, token, _ in requests
                                if url.startswith("http://127.0.0.1")))


if __name__ == "__main__":
    unittest.main()
