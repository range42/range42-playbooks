import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from range42_stack.install import prepare_node
from range42_stack.plan import build_plan
from test_plan import spec


class PackagingAcceptanceTests(unittest.TestCase):
    def test_cli_exports_two_native_stacks_and_rejects_conflicting_peer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, base, subnet, bridge in (("alpha", 31000, "10.81.0.0/24", "r42alpha"),
                                                ("bravo", 32000, "10.82.0.0/24", "r42bravo")):
                path = root / f"{name}.json"
                path.write_text(json.dumps(spec(name, base, subnet, bridge)))
                args = [sys.executable, "-m", "range42_stack", "--spec", str(path), "--output", str(root / name)]
                if name == "bravo":
                    args += ["--peer", str(root / "alpha/manifest/stack.json")]
                result = subprocess.run(args, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((root / name / "configure.yml").exists())
            result = subprocess.run([sys.executable, "-m", "range42_stack", "--spec", str(root / "alpha.json"),
                "--output", str(root / "conflict"), "--peer", str(root / "alpha/manifest/stack.json")],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "conflict").exists())

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is not installed")
    def test_application_owned_compose_resolves_with_instance_overrides(self):
        # These are real sibling application definitions, not copies of our implementation.
        workspace = Path(__file__).resolve().parents[4]
        backend = workspace / "range42-backend-api"
        reporting = workspace / "range42-reporting-tool"
        self.assertTrue((backend / "docker-compose.runtime.yml").is_file())
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            for service, repo in (("backend", backend), ("reporting", reporting)):
                root = base / service
                source = root / "source" / repo.name
                source.mkdir(parents=True)
                if service == "backend":
                    for filename in ("docker-compose.yml", "docker-compose.runtime.yml"):
                        shutil.copyfile(repo / filename, source / filename)
                    template = root / "template"
                    (template / "secrets").mkdir(parents=True, mode=0o700)
                    template.chmod(0o700)
                    for name, content in (("stack.json", '{"stack_id":"alpha"}'),
                            ("secrets/default_vault.yml", "$ANSIBLE_VAULT;1.1;AES256\nfixture"),
                            ("secrets/vault_pass.txt", "fixture")):
                        path = template / name
                        path.write_text(content)
                        path.chmod(0o600)
                else:
                    shutil.copytree(repo / "deploy", source / "deploy",
                                    ignore=shutil.ignore_patterns(".env", "*.pem", "*.key"))
                plan = build_plan(spec())
                prepare_node(plan, service, root)
                if service == "backend":
                    env = root / "private/backend.env"
                    self.assertIn("RANGE42_TRUSTED_PROXY_IPS='10.81.0.10'", env.read_text())
                    env.write_text(env.read_text().replace("/opt/range42/alpha/backend", str(root)))
                    args = ["--project-directory", str(source), "--env-file", str(env),
                            "-f", str(source / "docker-compose.yml"), "-f", str(source / "docker-compose.runtime.yml")]
                else:
                    deploy = source / "deploy"
                    args = ["--project-directory", str(deploy), "--env-file", str(root / "private/compose.env"),
                            "-f", str(deploy / "docker-compose.yml"), "-f", str(deploy / "docker-compose.prod.yml"),
                            "-f", str(root / "reporting.override.yml")]
                result = subprocess.run(["docker", "compose", "-p", "r42-alpha-" + service, *args, "config", "--format", "json"],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, service + ": " + result.stderr)
                doc = json.loads(result.stdout)
                if service == "backend":
                    api = doc["services"]["api"]
                    self.assertEqual(api["environment"]["RANGE42_AUTH_MODE"], "required")
                    self.assertEqual(api["environment"]["RANGE42_CORS_ORIGINS"], "https://ui.alpha.example.test")
                    self.assertEqual(api["ports"][0]["host_ip"], "10.81.0.11")
                    self.assertTrue(any(v["target"] == "/var/lib/range42" for v in api["volumes"]))
                    self.assertTrue(any(v["target"] == "/runtime" and v["read_only"] for v in api["volumes"]))
                else:
                    services = doc["services"]
                    self.assertFalse(services["postgres"].get("ports"))
                    self.assertFalse(services["backend"].get("ports"))
                    self.assertEqual(services["backend"]["depends_on"]["migrate"]["condition"], "service_completed_successfully")
                    self.assertEqual(services["caddy"]["ports"][0]["host_ip"], "10.81.0.14")
                    self.assertEqual(len(services["caddy"]["ports"]), 1)
                    self.assertNotEqual(services["postgres"]["environment"]["POSTGRES_PASSWORD"], "changeme")


if __name__ == "__main__":
    unittest.main()
