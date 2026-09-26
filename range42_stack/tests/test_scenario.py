import importlib
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import shutil

import yaml
from jinja2 import Environment, StrictUndefined

from range42_stack.plan import build_plan
from test_plan import spec


class ScenarioTests(unittest.TestCase):
    def compiler(self):
        self.assertTrue((Path(__file__).parents[1] / "scenario.py").exists(), "native platform compiler is missing")
        return importlib.import_module("range42_stack.scenario")

    def test_generated_native_scenario_installs_every_node_in_order(self):
        compiler = self.compiler()
        plan = build_plan(spec())
        files = compiler.render_scenario(plan)
        self.assertEqual(json.loads(files["manifest/scenario_vms.json"])["vms"][0]["vm_id"], 31000)
        self.assertEqual(json.loads(files["manifest/scenario_networks.json"])["vnets"][0]["vnet"], "r42alpha")
        plays = yaml.safe_load(files["configure.yml"])
        imports = [p["import_playbook"] for p in plays]
        self.assertLess(imports.index("nodes/backend.yml"), imports.index("nodes/gateway.yml"))
        for vm in plan["vms"]:
            self.assertIn(f"nodes/{vm['service']}.yml", files)
        self.assertIn("templates/ansible-inventory.j2", files)

    def test_children_receive_explicit_private_template_never_active_workspace(self):
        files = self.compiler().render_scenario(build_plan(spec()))
        preflight = yaml.safe_load(files["00_preflight.yml"])[0]
        self.assertEqual(preflight["vars"]["BUNDLE_STACK_TEMPLATE_DIR"], "{{ stack_credential_template_dir }}")
        for service in ("backend", "cli"):
            self.assertNotIn("RANGE42_ACTIVE_CONFIG_DIR", files[f"nodes/{service}.yml"])
        self.assertIn("/admin/platform.prepare.instance/main.yml", preflight["import_playbook"])

    def test_export_refuses_overwrite_and_contains_no_live_credentials(self):
        compiler = self.compiler()
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "alpha"
            compiler.export_scenario(build_plan(spec()), output)
            self.assertFalse((output / "_platform").exists(), "Helpers belong to the shared bundles, not scenario copies")
            before = (output / "main.yml").read_bytes()
            with self.assertRaises(FileExistsError):
                compiler.export_scenario(build_plan(spec()), output)
            self.assertEqual(before, (output / "main.yml").read_bytes())
            self.assertFalse((output / "secrets").exists())

    def test_preflight_rejects_foreign_vm_and_network_ownership(self):
        compiler = self.compiler()
        plan = build_plan(spec())
        compiler.validate_live(plan, [], [], [], [])
        with self.assertRaises(ValueError):
            compiler.validate_live(plan, [{"vmid": 31000, "name": "unrelated", "node": "pve"}], [], [], [])
        with self.assertRaises(ValueError):
            compiler.validate_live(plan, [], [{"vnet": "r42alpha", "zone": "other"}], [], [])
        with self.assertRaises(ValueError):
            compiler.validate_live(plan, [], [], [{"zone": plan["zone"], "type": "vlan"}], [])
        with self.assertRaises(ValueError):
            compiler.validate_live(plan, [], [], [], [{"cidr": "10.81.0.0/25", "vnet": "foreign"}])

    def test_configure_action_cannot_bypass_preflight_or_start_before_firewall(self):
        files = self.compiler().render_scenario(build_plan(spec()))
        self.assertEqual(yaml.safe_load(files["configure.yml"])[0]["import_playbook"], "00_preflight.yml")
        calls = [p["import_playbook"] for p in yaml.safe_load(files["nodes/backend.yml"])]
        self.assertLess(next(i for i,p in enumerate(calls) if "os_firewall.isolate.platform" in p),
                        next(i for i,p in enumerate(calls) if "software.install.deployer_api_backend" in p))

    def test_wazuh_dashboard_and_api_use_instance_credentials(self):
        calls = yaml.safe_load(self.compiler().render_scenario(build_plan(spec()))["nodes/wazuh.yml"])
        install = calls[-1]
        self.assertIn("/alpha/wazuh/private/wazuh.yml", install["vars"]["BUNDLE_WAZUH_VARS_FILE"])
        self.assertTrue(install["vars"]["BUNDLE_WAZUH_API_PASSWORDS"])
        self.assertIn('default(', install['vars']['BUNDLE_WAZUH_CERTS_DIR'])
        self.assertIn('/alpha/wazuh/certificates', install['vars']['BUNDLE_WAZUH_CERTS_DIR'])

    def test_wazuh_preflight_requires_room_beyond_its_four_gib_heap(self):
        compiler = self.compiler()
        self.assertTrue(hasattr(compiler, 'validate_template_capacity'))
        plan = build_plan(spec())
        with self.assertRaisesRegex(ValueError, 'Wazuh'):
            compiler.validate_template_capacity(plan, {'memory': 4096}, {})
        compiler.validate_template_capacity(plan, {'memory': 8192}, {})
        compiler.validate_template_capacity(plan, {'memory': 4096}, {'wazuh': False})

    def test_native_inventory_defers_job_parameters_until_execution(self):
        files = self.compiler().render_scenario(build_plan(spec()))
        # Native inventory preparation receives context metadata, before job parameters.
        rendered = Environment(undefined=StrictUndefined).from_string(files["templates/ansible-inventory.j2"]).render()
        self.assertEqual(yaml.safe_load(rendered), yaml.safe_load(files["hosts.yml"]))
        self.assertIn("templates/ssh-config.j2", files)
        ssh = Environment(undefined=StrictUndefined).from_string(files["templates/ssh-config.j2"]).render(
            INFRASTRUCTURE_CODENAME="parent", INFRASTRUCTURE_SCENARIO="lab", INFRASTRUCTURE_PROXMOX_ADDRESS="pve.example.test",
            DEPLOYER_CLI__DST_SSH_KEYS_BACKEND_DEST_DIR="/private/backend",
            DEPLOYER_CLI__DST_SSH_KEYS_JUMP_DEST_DIR="/private/jump")
        self.assertIn("Host r42-alpha-backend 10.81.0.11", ssh)
        self.assertIn("ProxyJump r42-stack-jump", ssh)

    def test_preflight_rejects_foreign_guests_attached_to_the_stack_network(self):
        compiler = self.compiler()
        plan = build_plan(spec())
        with self.assertRaises(ValueError):
            compiler.validate_live(plan, [{"vmid": 40000, "name": "foreign", "node": "pve",
                                          "config": {"net0": "virtio,bridge=r42alpha"}}], [], [], [])

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required")
    def test_tls_identity_must_cover_the_stack_domain_and_match_its_key(self):
        compiler = self.compiler()
        self.assertTrue(hasattr(compiler, "validate_tls"), "TLS identity validation is missing")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-subj", "/CN=*.alpha.example.test", "-addext", "subjectAltName=DNS:*.alpha.example.test",
                "-keyout", str(root / "key.pem"), "-out", str(root / "cert.pem")],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            (root / "key.pem").chmod(0o600)
            compiler.validate_tls(root, "alpha.example.test")
            with self.assertRaises(ValueError):
                compiler.validate_tls(root, "bravo.example.test")
            subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-out", str(root / "key.pem")],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with self.assertRaises(ValueError):
                compiler.validate_tls(root, "alpha.example.test")


if __name__ == "__main__":
    unittest.main()
