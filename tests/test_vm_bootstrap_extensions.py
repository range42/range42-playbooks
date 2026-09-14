"""Run the actual bootstrap bundle against a local HTTPS Proxmox simulator."""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
from urllib.parse import parse_qs

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = Path(os.environ.get("RANGE42_CONTROLLER_TEST_ROOT", "/tmp/r42-sdn-controller-integration"))


@contextlib.contextmanager
def proxmox_api(tmp_path, *, description=None, disk="local-lvm:vm-5001-disk-0,size=8G"):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
                   .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
                   .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                   .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "ca.pem", tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)
    state = {"exists": description is not None, "config": {"name": "test-vm", "description": description or "", "scsi0": disk,
             "cores": 1, "memory": 512, "net0": "virtio=AA:BB:CC:DD:EE:01,bridge=vmbr0", "digest": "digest-0"},
             "mutations": [], "started": False, "resize_count": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def respond(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": data}).encode())
        def do_GET(self):
            if "/tasks/" in self.path:
                self.respond({"status": "stopped", "exitstatus": "OK"})
            elif self.path.endswith("/status/current"):
                self.respond({"name": "test-vm", "status": "running" if state["started"] else "stopped"}, 200 if state["exists"] else 500)
            elif self.path.endswith("/config"):
                self.respond(state["config"])
            else:
                self.respond({}, 404)
        def mutate(self):
            data = {name: values[0] for name, values in parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode(), keep_blank_values=True).items()}
            state["mutations"].append((self.command, self.path, data))
            if "digest" in data and data["digest"] != state["config"]["digest"]:
                self.respond({"error": "stale digest"}, 409)
                return
            if self.path.endswith("/clone"):
                state["exists"] = True
                state["config"]["description"] = data.get("description", "")
            elif self.path.endswith("/config"):
                state["config"].update({key: value for key, value in data.items() if key != "digest"})
                state["config"]["digest"] = f"digest-{len(state['mutations'])}"
            elif self.path.endswith("/resize"):
                state["resize_count"] += 1
                state["config"][data["disk"]] = f"local-lvm:vm-5001-disk-0,size={data['size']}"
                self.respond("UPID:local:resize")
                return
            elif self.path.endswith("/status/start"):
                state["started"] = True
            self.respond(None)
        do_POST = mutate
        do_PUT = mutate

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, server.server_port, cert_path
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def bootstrap(tmp_path, port, ca, **overrides):
    binary = Path(sys.executable).with_name("ansible-playbook")
    assert binary.exists(), "Run with an environment that provides ansible-playbook"
    inventory = tmp_path / "hosts.ini"
    inventory.write_text(f"[proxmox]\npve ansible_connection=local ansible_python_interpreter={sys.executable}\n[cli]\npve-cli ansible_connection=local ansible_python_interpreter={sys.executable}\n")
    vault = tmp_path / "config/secrets/default_vault.yml"
    vault.parent.mkdir(parents=True, exist_ok=True)
    vault.write_text("{}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    qm = bin_dir / "qm"
    qm.write_text("#!/bin/sh\necho 'name: test-vm'\n")
    qm.chmod(0o700)
    variables = {"proxmox_api_host": f"127.0.0.1:{port}", "proxmox_node": "pve", "proxmox_api_user": "test@pve",
                 "proxmox_api_token_id": "test", "proxmox_api_token_secret": "test", "proxmox_api_validate_certs": True,
                 "global_vm_id": 5001, "global_template_vm_id": 9000, "global_vm_name": "test-vm", "global_vm_tag_name": "test",
                 "global_vm_ssh_name": "no-guests-for-this-test", "global_vm_ci_ip": "10.42.9.10", "global_vm_ci_ip_gw": "10.42.9.1",
                 "global_vm_net_virtio_bridge": "vmbr0", "default_admin_vm_ci_ssh_key": "ssh-ed25519 AAAATEST",
                 "default_admin_vm_ci_password": "test-only-password", "r42_deployment_id": "owned",
                 "global_vm_description": "range42-deployment:owned", **overrides}
    extra = tmp_path / "vars.json"
    extra.write_text(json.dumps(variables))
    environment = {**os.environ, "RANGE42_ACTIVE_CONFIG_DIR": str(tmp_path / "config"),
                   "RANGE42_PROXMOX_CA_FILE": str(ca), "SSL_CERT_FILE": str(ca),
                   "ANSIBLE_ROLES_PATH": str(CONTROLLER / "roles"), "ANSIBLE_NOCOLOR": "1",
                   "ANSIBLE_HOST_KEY_CHECKING": "False", "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    wrapper = tmp_path / "scenario.yml"
    wrapper.write_text(f'- import_playbook: "{ROOT / "bundles/proxmox/vm.bootstrap/main.yml"}"\n')
    return subprocess.run([str(binary), "-i", str(inventory), str(wrapper), "-e", f"@{extra}"],
                          env=environment, text=True, capture_output=True, timeout=90)


def test_bootstrap_rejects_existing_vm_without_exact_ownership_before_mutation(tmp_path):
    with proxmox_api(tmp_path, description="range42-deployment:owned-extra") as (state, port, ca):
        result = bootstrap(tmp_path, port, ca)
        assert result.returncode != 0, result.stdout[-5000:]
        assert state["mutations"] == [], "An unrelated existing VM must not be tagged, configured or started"


def test_bootstrap_applies_secondary_nic_resources_and_grows_vm_disk_before_start(tmp_path):
    with proxmox_api(tmp_path) as (state, port, ca):
        result = bootstrap(tmp_path, port, ca, global_vm_extra_config={"cores": 4, "memory": 2048,
                           "net1": "virtio,bridge=r42net", "ipconfig1": "ip=10.42.20.10/24"},
                           global_vm_disk={"disk": "scsi0", "size_gb": 20})
        assert result.returncode == 0, result.stdout[-8000:] + result.stderr[-2000:]
        assert state["config"].get("net1") == "virtio,bridge=r42net"
        assert state["config"].get("ipconfig1") == "ip=10.42.20.10/24"
        assert str(state["config"]["cores"]) == "4"
        assert str(state["config"]["memory"]) == "2048"
        assert state["resize_count"] == 1
        mutations = state["mutations"]
        resize = next(index for index, item in enumerate(mutations) if item[1].endswith("/resize"))
        start = next(index for index, item in enumerate(mutations) if item[1].endswith("/status/start"))
        assert resize < start
        assert "digest" in mutations[resize][2]
        assert any(item[1].endswith("/cloudinit") for item in mutations[resize + 1:start])


@pytest.mark.parametrize("disk,size", [("local-lvm:vm-5001-disk-0,size=8G", 4),
                                      ("local:iso/debian.iso,media=cdrom,size=8G", 20),
                                      ("local-lvm:base-9000-disk-0,size=8G", 20)])
def test_bootstrap_refuses_disk_shrink_cdrom_and_source_images(tmp_path, disk, size):
    with proxmox_api(tmp_path, disk=disk) as (state, port, ca):
        result = bootstrap(tmp_path, port, ca, global_vm_disk={"disk": "scsi0", "size_gb": size})
        assert result.returncode != 0
        assert state["resize_count"] == 0
        assert not state["started"]


def test_primary_nic_has_explicit_stable_mac_when_bridge_is_updated(tmp_path):
    with proxmox_api(tmp_path) as (state, port, ca):
        result = bootstrap(tmp_path, port, ca, vm_net_virtio_mac="52:54:00:aa:bb:cc")
        assert result.returncode == 0, result.stdout[-5000:] + result.stderr[-1000:]
        assert "52:54:00:aa:bb:cc" in state["config"]["net0"]
