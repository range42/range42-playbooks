"""Exercise the native bootstrap with the matching controller and a recording API."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundles/proxmox/vm.bootstrap"


class BootstrapTests(unittest.TestCase):
    def run_bootstrap(self, extra, template_config=None):
        roles = os.environ.get("RANGE42_TEST_CONTROLLER_ROLES")
        self.assertTrue(roles, "Set RANGE42_TEST_CONTROLLER_ROLES to the matching controller roles directory")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            library.mkdir()
            (library / "uri.py").write_text('''from ansible.module_utils.basic import AnsibleModule
import json, os
m = AnsibleModule(argument_spec={k: {"type": "raw"} for k in
    ["url", "method", "headers", "validate_certs", "body_format", "body", "status_code", "return_content"]})
template = m.params["url"].endswith("/qemu/9000/config")
initial_probe = m.params["url"].endswith("/status/current") and not any(
    json.loads(line)["url"].endswith("/status/current") for line in
    open(os.environ["BOOTSTRAP_REQUEST_LOG"]) if line.strip()) if os.path.exists(os.environ["BOOTSTRAP_REQUEST_LOG"]) else True
with open(os.environ["BOOTSTRAP_REQUEST_LOG"], "a") as f:
    f.write(json.dumps(m.params) + "\\n")
m.exit_json(changed=m.params["method"] != "GET", status=500 if initial_probe and not template else 200,
    json={"data": json.loads(os.environ["BOOTSTRAP_TEMPLATE_CONFIG"]) if template else {"status": "stopped", "name": "application"}})
''')
            # qm is used only by the read-only post-clone lock probe.
            (root / "qm").write_text("#!/bin/sh\nexit 0\n")
            (root / "qm").chmod(0o755)
            play = yaml.safe_load((BUNDLE / "main.yml").read_text())[0]
            play["hosts"] = "localhost"
            play["connection"] = "local"
            play.pop("vars_files")
            play["vars"] = {
                "proxmox_api_host": "never-contact.example", "proxmox_node": "node",
                "proxmox_api_user": "test", "proxmox_api_token_id": "test",
                "proxmox_api_token_secret": "test", "default_admin_vm_ci_ssh_key": "ssh-ed25519 test",
                "global_vm_id": 60020, "global_template_vm_id": 9000,
                "global_vm_name": "application", "global_vm_tag_name": "exercise",
                "global_vm_ci_ip": "10.42.10.10", "global_vm_ci_ip_gw": "10.42.10.1",
                "global_vm_net_virtio_bridge": "blue1", "global_vm_extra_config": extra,
            }
            (root / "play.yml").write_text(yaml.safe_dump([play]))
            (root / "hosts.yml").write_text(yaml.safe_dump({"all": {"hosts": {
                "localhost": {"ansible_connection": "local"},
                "localhost-cli": {"ansible_connection": "local"}}}}))
            log = root / "requests.jsonl"
            executable = shutil.which("ansible-playbook")
            self.assertIsNotNone(executable, "ansible-playbook must be on PATH")
            result = subprocess.run([executable, "-i", str(root / "hosts.yml"), str(root / "play.yml")],
                text=True, capture_output=True, env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
                    "ANSIBLE_ROLES_PATH": roles, "ANSIBLE_LIBRARY": str(library),
                    "BOOTSTRAP_TEMPLATE_CONFIG": json.dumps(template_config if template_config is not None else {"net0": "virtio,bridge=vmbr0"}),
                    "BOOTSTRAP_REQUEST_LOG": str(log), "ANSIBLE_NOCOLOR": "1"})
            requests = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, requests

    def test_full_bootstrap_applies_extra_nic_and_resources_before_start(self):
        extra = {"net1": "virtio,bridge=red1", "ipconfig1": "ip=10.42.11.10/24", "cores": 4, "memory": 4096}
        result, requests = self.run_bootstrap(extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config_index, config = next((i, row["body"]) for i, row in enumerate(requests)
            if row["method"] == "PUT" and row["url"].endswith("/config"))
        self.assertEqual({key: config.get(key) for key in extra}, extra)
        clone_index = next(i for i, row in enumerate(requests) if row["url"].endswith("/clone"))
        start_index = next(i for i, row in enumerate(requests) if row["url"].endswith("/status/start"))
        regen_index = next(i for i, row in enumerate(requests) if row["url"].endswith("/cloudinit"))
        self.assertLess(clone_index, config_index)
        self.assertLess(config_index, regen_index)
        self.assertLess(regen_index, start_index)

    def test_invalid_extra_config_fails_before_clone_or_any_other_api_call(self):
        result, requests = self.run_bootstrap({"delete": "scsi0"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(requests, [])

    def test_unplanned_template_interface_is_rejected_before_clone(self):
        result, requests = self.run_bootstrap({}, {"net0": "virtio,bridge=vmbr0", "net1": "virtio,bridge=shared"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(requests)
        self.assertTrue(all(row["method"] == "GET" for row in requests))

    def test_authored_interface_replaces_matching_template_interface(self):
        extra = {"net1": "virtio,bridge=red1", "ipconfig1": "ip=10.42.11.10/24"}
        result, requests = self.run_bootstrap(extra, {"net0": "virtio,bridge=vmbr0", "net1": "virtio,bridge=shared"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = next(row["body"] for row in requests if row["method"] == "PUT" and row["url"].endswith("/config"))
        self.assertEqual(config["net1"], extra["net1"])

    def test_advertises_only_implemented_bootstrap_features(self):
        path = BUNDLE / "capabilities.json"
        self.assertTrue(path.is_file(), "Bootstrap must advertise verified optional inputs")
        self.assertEqual(json.loads(path.read_text()), {
            "version": 1, "features": ["extra_nics", "resources"], "requires_native_contract": True})


if __name__ == "__main__":
    unittest.main()
