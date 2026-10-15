"""Execute the real native unlock task against a disposable, verified TLS API."""

from collections import deque
import copy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bundles/proxmox/vm.bootstrap/main.yml"
SECRET = "synthetic-private-api-token-do-not-publish"


def unlock_task():
    plays = yaml.safe_load(SOURCE.read_text())
    return copy.deepcopy(
        next(
            task
            for task in plays[0]["tasks"]
            if "WAIT FOR PROXMOX UNLOCK" in task.get("name", "")
        )
    )


@pytest.fixture(scope="module")
def certificate(tmp_path_factory):
    directory = tmp_path_factory.mktemp("native-unlock-tls")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path, key_path = directory / "ca.pem", directory / "key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    return certificate_path, key_path


@pytest.fixture
def endpoint(certificate):
    replies = deque([(200, {"data": {}})])
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(
                {"path": self.path, "authorization": self.headers.get("Authorization")}
            )
            status, body = replies[0]
            if len(replies) > 1:
                replies.popleft()
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *arguments):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(*map(str, certificate))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "host": f"localhost:{server.server_port}",
            "ca": str(certificate[0]),
            "replies": replies,
            "requests": requests,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def execute(tmp_path, endpoint, *, cli_fixture=False, trusted=True, host=None):
    task = unlock_task()
    # Shorten only retry timing; the current task, module and predicates remain authoritative.
    task["retries"], task["delay"] = 2, 0
    binary_directory = tmp_path / "bin"
    binary_directory.mkdir()
    ssh = binary_directory / "ssh"
    ssh.write_text("#!/bin/sh\necho forbidden-hypervisor-ssh >&2\nexit 73\n")
    ssh.chmod(0o700)
    qm = binary_directory / "qm"
    qm.write_text("#!/bin/sh\necho 'permission denied: qm requires root' >&2\nexit 2\n")
    qm.chmod(0o700)
    hosts = {
        "fixture": {
            "ansible_connection": "local",
            "ansible_python_interpreter": shutil.which("python3"),
        }
    }
    if cli_fixture:
        hosts["fixture-cli"] = {
            "ansible_connection": "local",
            "ansible_python_interpreter": shutil.which("python3"),
        }
    inventory = tmp_path / "hosts.yml"
    inventory.write_text(yaml.safe_dump({"all": {"hosts": hosts}}))
    configuration = tmp_path / "ansible.cfg"
    configuration.write_text(
        f"[defaults]\nhost_key_checking=True\nretry_files_enabled=False\n[ssh_connection]\nssh_executable={ssh}\n"
    )
    variables = {
        "global_vm_id": 42190,
        "global_vm_name": "unlock-fixture",
        "proxmox_node": "pve42-1",
        "proxmox_api_host": host or endpoint["host"],
        "proxmox_api_user": "fixture@pve",
        "proxmox_api_token_id": "bootstrap",
        "proxmox_api_token_secret": SECRET,
        "proxmox_api_validate_certs": True,
    }
    play = tmp_path / "probe.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "fixture",
                    "gather_facts": False,
                    "vars": variables,
                    "environment": {
                        "PATH": str(binary_directory) + os.pathsep + os.environ["PATH"]
                    },
                    "tasks": [task],
                }
            ],
            sort_keys=False,
        )
    )
    environment = dict(
        os.environ,
        ANSIBLE_CONFIG=str(configuration),
        RANGE42_PROXMOX_CA_FILE=endpoint["ca"] if trusted else "",
        SSL_CERT_FILE=endpoint["ca"]
        if trusted
        else ssl.get_default_verify_paths().openssl_cafile,
        ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-tmp"),
    )
    environment.pop("SSH_AUTH_SOCK", None)
    environment.pop("ANSIBLE_VAULT_PASSWORD_FILE", None)
    result = subprocess.run(
        ["ansible-playbook", "-i", str(inventory), str(play)],
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert SECRET not in result.stdout + result.stderr, (
        "Unlock task published its API authorization secret"
    )
    return result


def test_failed_qm_read_is_not_accepted_as_unlocked(tmp_path, endpoint):
    endpoint["replies"].clear()
    endpoint["replies"].append((403, {"errors": {"permission": "denied"}}))
    result = execute(tmp_path, endpoint, cli_fixture=True)
    assert result.returncode != 0, (
        "A failed configuration read was accepted as an unlocked VM"
    )


def test_locked_then_unlocked_uses_verified_api_with_no_hypervisor_ssh(
    tmp_path, endpoint
):
    endpoint["replies"].clear()
    endpoint["replies"].extend(
        [(200, {"data": {"lock": "clone"}}), (200, {"data": {}})]
    )
    result = execute(tmp_path, endpoint)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(endpoint["requests"]) == 2
    assert all(
        request
        == {
            "path": "/api2/json/nodes/pve42-1/qemu/42190/config",
            "authorization": "PVEAPIToken=fixture@pve!bootstrap=" + SECRET,
        }
        for request in endpoint["requests"]
    )
    assert "forbidden-hypervisor-ssh" not in result.stdout + result.stderr


@pytest.mark.parametrize("status", [401, 403, 500])
def test_api_errors_cannot_be_accepted_as_unlocked(tmp_path, endpoint, status):
    endpoint["replies"].clear()
    endpoint["replies"].append(
        (status, {"data": {}, "error": "synthetic refused API read"})
    )
    result = execute(tmp_path, endpoint)
    assert result.returncode != 0
    assert endpoint["requests"], "The authoritative API read was not attempted"


@pytest.mark.parametrize(
    "body", [b"not-json", [], {}, {"data": None}, {"data": []}, {"data": "unlocked"}]
)
def test_missing_or_malformed_config_cannot_be_accepted_as_unlocked(
    tmp_path, endpoint, body
):
    endpoint["replies"].clear()
    endpoint["replies"].append((200, body))
    result = execute(tmp_path, endpoint)
    assert result.returncode != 0
    assert endpoint["requests"]


@pytest.mark.parametrize("lock", ["clone", None, "", False])
def test_lock_field_must_be_absent_and_held_lock_times_out(tmp_path, endpoint, lock):
    endpoint["replies"].clear()
    endpoint["replies"].append((200, {"data": {"lock": lock}}))
    result = execute(tmp_path, endpoint)
    assert result.returncode != 0
    assert len(endpoint["requests"]) == 3


def test_untrusted_certificate_blocks_before_authenticated_request(tmp_path, endpoint):
    result = execute(tmp_path, endpoint, trusted=False)
    assert result.returncode != 0
    assert endpoint["requests"] == []


def test_certificate_hostname_mismatch_blocks_before_authenticated_request(
    tmp_path, endpoint
):
    result = execute(
        tmp_path, endpoint, host=endpoint["host"].replace("localhost", "127.0.0.1")
    )
    assert result.returncode != 0
    assert endpoint["requests"] == []
