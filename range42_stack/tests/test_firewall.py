import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from range42_stack.plan import build_plan
from test_plan import spec


class FirewallTests(unittest.TestCase):
    def renderer(self):
        self.assertTrue((Path(__file__).parents[1] / "firewall.py").exists(), "guest ingress policy is missing")
        return importlib.import_module("range42_stack.firewall")

    def test_backend_docker_ingress_accepts_own_gateway_only(self):
        rules = self.renderer().render_firewall(build_plan(spec()), "backend", "ens18", {
            "management": ["192.168.50.0/24"], "clients": ["0.0.0.0/0"], "agents": []})
        self.assertIn('iifname "ens18" ct status dnat ip saddr 10.81.0.10 accept', rules)
        self.assertIn('iifname "ens18" ct status dnat drop', rules)
        self.assertNotIn("flush ruleset", rules)
        self.assertNotIn("0.0.0.0/0", rules)
        self.assertIn("192.168.50.0/24", rules)
        self.assertIn("tcp dport 22 accept", rules)

    def test_gateway_exposes_only_the_requested_client_networks(self):
        rules = self.renderer().render_firewall(build_plan(spec()), "gateway", "ens18", {
            "management": ["192.168.50.0/24"], "clients": ["192.168.60.0/24"], "agents": []})
        self.assertIn("192.168.60.0/24", rules)
        self.assertNotIn("0.0.0.0/0", rules)
        self.assertIn("ip saddr { 192.168.60.0/24 } tcp dport 443 accept", rules)

    def test_rejects_empty_management_and_rule_injection(self):
        renderer = self.renderer()
        for interface, management in [("ens18; flush ruleset", ["10.0.0.0/24"]), ("ens18", []),
                                       ("ens18", ["10.0.0.0/24; accept"])]:
            with self.assertRaises(ValueError):
                renderer.render_firewall(build_plan(spec()), "backend", interface,
                                         {"management": management, "clients": [], "agents": []})

    def test_exported_claim_command_runs_before_payload_copy(self):
        from range42_stack.scenario import export_scenario
        with tempfile.TemporaryDirectory() as temp:
            scenario, root = Path(temp) / "scenario", Path(temp) / "backend"
            export_scenario(build_plan(spec()), scenario)
            result = subprocess.run([sys.executable, "-m", "range42_stack.install", "claim", "--plan",
                str(scenario / "manifest/stack.json"), "--root", str(root), "--service", "backend"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root / "owner.json").read_text())["stack_id"], "alpha")
            self.assertFalse((root / "compose.yml").exists())


if __name__ == "__main__":
    unittest.main()
