"""Opt-in native installation acceptance using disposable containers only."""
import copy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import uuid

from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import httpx
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT.parent
BUNDLE = ROOT / "bundles/admin/software.install.deployer_api_backend"
IMAGE = os.getenv("RANGE42_NATIVE_API_INSTALL_TEST_IMAGE")
pytestmark = pytest.mark.skipif(not IMAGE, reason="set RANGE42_NATIVE_API_INSTALL_TEST_IMAGE for disposable Docker acceptance")


def private_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(value if isinstance(value, bytes) else value.encode())
    path.chmod(0o600)


def test_native_bundle_fresh_running_refusal_stopped_repeat_and_native_execution(tmp_path):
    name = "r42-native-install-" + uuid.uuid4().hex[:10]
    project = tmp_path / name
    project.mkdir()
    home, workspaces, state, credentials, template = [tmp_path / x for x in ("home", "workspaces", "state", "credentials", "template")]
    for directory in (home, workspaces, state, credentials, template):
        directory.mkdir(mode=0o700)
    token = secrets.token_hex(32)
    private_file(credentials / "api-token", token)
    private_file(credentials / "credential-key", Fernet.generate_key())
    original_credentials = {p.name: p.read_bytes() for p in credentials.iterdir()}
    context = workspaces / "fixture-smoke"
    (context / "inventory").mkdir(parents=True, mode=0o700)
    private_file(context / "sourced_range42.sh", '''export RANGE42_INFRASTRUCTURE_CODENAME="fixture"
export RANGE42_INFRASTRUCTURE_LAB="smoke"
export RANGE42_GITDIR__ROOT_DIR="/runtime"
export RANGE42_CONFIG_BASE_DIR="/home/range42/range42.config"
export RANGE42_ANSIBLE_ROLES__DEVKITS_DIR="/runtime/range42-ansible_roles-debug-devkit"
''')
    private_file(context / "inventory/inventory_default.yml", "all:\n  children:\n    proxmox:\n      hosts:\n        fixture:\n          ansible_host: proxmox-fixture:8443\n          ansible_connection: local\n")
    private_file(context / "secrets/vault_pass.txt", "synthetic-vault-password")
    private_file(context / "secrets/default_vault.yml", "fixture_marker: native-context\n")
    subprocess.run(["ansible-vault", "encrypt", "--vault-password-file", str(context / "secrets/vault_pass.txt"),
                    str(context / "secrets/default_vault.yml")], capture_output=True, check=True)
    for path in (context / "secrets").iterdir():
        private_file(template / "secrets" / path.name, path.read_bytes())
    private_file(home / ".zshrc", "")
    private_file(home / ".ssh/config", "#### BEGIN RANGE42 INCLUDE\nInclude /home/range42/.ssh/config_range42-fixture-smoke\n#### END RANGE42 INCLUDE\n")
    private_file(home / ".ssh/config_range42-fixture-smoke", "Host fixture\n    HostName proxmox-fixture\n    IdentityFile none\n")
    fixture_repo = home / "native-smoke"
    scenario = fixture_repo / "scenarios/smoke"
    (scenario / "manifest").mkdir(parents=True)
    (scenario / "templates").mkdir()
    (scenario / "manifest/scenario_vms.json").write_text('{"version":2,"vms":[]}')
    (scenario / "templates/ansible-inventory.j2").write_text("all:\n  hosts:\n    localhost:\n      ansible_connection: local\n")
    (scenario / "main.yml").write_text("- hosts: localhost\n  gather_facts: false\n  tasks:\n"
        "    - ansible.builtin.include_tasks: /runtime/range42-catalog/02_ansible_layer/admin/roles/ansible.utils/tasks/wait/openssh_server/is_reachable.yml\n"
        "    - ansible.builtin.debug:\n        msg: native-localhost-only\n")
    (scenario / "smoke.setup.sh").write_text('ansible-playbook -i "$RANGE42_ANSIBLE_ROLES__INVENTORY_DIR/inventory_default.yml" ./main.yml\n')
    (context / "scenario").symlink_to("/home/range42/native-smoke/scenarios/smoke")

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    for component in ("range42", "range42-playbooks", "range42-catalog",
                      "range42-ansible_roles-proxmox_controller", "range42-ansible_roles-debug-devkit"):
        shutil.copytree(SOURCES / component, runtime / component, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache", ".ruff_cache"))
    (runtime / "ansible.cfg").write_text("[defaults]\nhost_key_checking = True\nretry_files_enabled = False\n")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "proxmox-fixture")])
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=5))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("proxmox-fixture")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(key, hashes.SHA256()))
    tls = tmp_path / "tls"
    private_file(tls / "cert.pem", certificate.public_bytes(serialization.Encoding.PEM))
    private_file(tls / "key.pem", key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (runtime / "proxmox-ca.pem").write_bytes(Path("/etc/ssl/certs/ca-certificates.crt").read_bytes() + (tls / "cert.pem").read_bytes())
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        port = connection.getsockname()[1]
    image = "range42-native-install-test:" + uuid.uuid4().hex[:10]
    client_config = tmp_path / "docker-client"
    client_config.mkdir()
    env = {**os.environ, "DOCKER_CONFIG": str(client_config), "RANGE42_ACTIVE_WORKSPACE": "fixture-smoke",
           "RANGE42_ACTIVE_CONFIG_DIR": str(context), "RANGE42_INFRASTRUCTURE_CODENAME": "fixture",
           "RANGE42_GITDIR__ROOT_DIR": str(SOURCES)}
    variables = {"global_vm_ssh_name": "localhost", "global_vm_ci_ip": "127.0.0.1",
        "LOCAL_CODE_PATH": str(SOURCES / "range42-backend-api") + "/", "REMOTE_PROJECT_DIR": str(project),
        "API_PORT": port, "API_CONTAINER_IMAGE": image, "BACKEND_LISTEN_ADDRESS": "127.0.0.1",
        "BACKEND_CORS_ORIGINS": "https://staff.example.test", "API_CONTAINER_UID": os.getuid(),
        "API_CONTAINER_GID": os.getgid(), "API_SECRETS_DIR_HOST": str(credentials),
        "API_HOME_DIR_HOST": str(home), "API_STATE_DIR_HOST": str(state), "WORKSPACE_DIR_HOST": str(workspaces),
        "RUNTIME_DIR_HOST": str(runtime), "WORKSPACE_TEMPLATE_DIR_HOST": str(template),
        "proxmox_api_host": "proxmox-fixture:8443", "proxmox_node": "fixture",
        "proxmox_api_user": "fixture@pve", "proxmox_api_token_id": "test",
        "proxmox_api_token_secret": "not-live-proxmox-token"}
    plays = yaml.safe_load((BUNDLE / "main.yml").read_text())

    def ansible(selected, *, expect_success=True):
        document = []
        for play in selected:
            item = copy.deepcopy(play)
            item.update({"hosts": "localhost", "connection": "local", "become": False, "gather_facts": False})
            item.pop("vars_files", None)
            item.pop("tags", None)
            item["vars"] = {**item.get("vars", {}), **variables}
            for task in item.get("tasks", []):
                # The fixture is an unprivileged local transport, not a target VM.
                for module in ("ansible.builtin.copy", "ansible.builtin.file"):
                    if module in task and task[module].get("owner") == "root":
                        task[module].pop("owner", None)
                        task[module].pop("group", None)
            document.append(item)
        fixture = tmp_path / "fixture.yml"
        fixture.write_text(yaml.safe_dump(document, sort_keys=False, width=1000))
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(fixture)], env=env,
                                capture_output=True, text=True, timeout=240)
        (tmp_path / "last-ansible.log").write_text(result.stdout + result.stderr)
        if expect_success:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout
        assert token not in result.stdout + result.stderr
        assert "not-live-proxmox-token" not in result.stdout + result.stderr
        return result

    compose = ["docker", "compose", "--project-directory", str(project), "-f", str(project / "docker-compose.yml"),
               "-f", str(project / "docker-compose.runtime.yml"), "-f", str(project / "docker-compose.override.yml")]

    def command(argv):
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    fake = name + "-proxmox"
    scratch = name + "-collections"
    try:
        command(["docker", "tag", IMAGE, image])
        command(["docker", "create", "--name", scratch, image])
        command(["docker", "cp", scratch + ":/usr/share/ansible/collections", str(runtime / "collections")])
        command(["docker", "rm", scratch])
        for filename in ("docker-compose.yml", "docker-compose.runtime.yml"):
            shutil.copyfile(SOURCES / "range42-backend-api" / filename, project / filename)
        render = copy.deepcopy(plays[4])
        render["tasks"] = [t for t in render["tasks"] if t.get("name", "").startswith(("Render .env", "Render docker-compose.override"))]
        ansible([render])
        profile_code = """import json
from pathlib import Path
from app.core.bundle_runtime import build_runtime_manifest
components={name:Path('/runtime')/part for name,part in {
'playbooks':'range42-playbooks','controller':'range42-ansible_roles-proxmox_controller',
'catalog':'range42-catalog','range42':'range42','devkit':'range42-ansible_roles-debug-devkit',
'collections':'collections','ansible_config':'ansible.cfg'}.items()}
print(json.dumps(build_runtime_manifest(components)))"""
        (runtime / "bundle-runtime.json").write_text(command(compose + ["run", "--rm", "--no-deps", "--entrypoint", "python", "api", "-c", profile_code]))
        server = """import http.server,ssl,json
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  authorized=self.headers.get('Authorization')=='PVEAPIToken=fixture@pve!test=not-live-proxmox-token'
  self.send_response(200 if authorized else 401);self.end_headers()
  self.wfile.write(json.dumps({'data':{'version':'fixture'}}).encode())
 def log_message(self,*args):pass
server=http.server.HTTPServer(('0.0.0.0',8443),Handler)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain('/fixture/cert.pem','/fixture/key.pem')
server.socket=context.wrap_socket(server.socket,server_side=True);server.serve_forever()"""
        command(["docker", "run", "-d", "--name", fake, "--network", name + "_default", "--network-alias", "proxmox-fixture",
                 "--mount", f"type=bind,src={tls},dst=/fixture,readonly", "--entrypoint", "python", image, "-c", server])
        ansible([plays[0]])
        packaging = copy.deepcopy(plays[4])
        packaging["tasks"] = [t for t in packaging["tasks"] if t.get("name") != "Install rsync"]
        ansible([packaging, plays[5]])
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False) as client:
            headers = {"Authorization": "Bearer " + token}
            assert client.get("/docs/openapi.json").status_code == 401
            assert client.get("/v1/health/ready", headers=headers).json()["ready"] is True
            hosts = client.get("/v1/proxmox/hosts", headers=headers).json()
            host_id = hosts["items"][0]["id"]
            first = command(compose + ["ps", "-q", "api"])
            env_before = (project / ".env").read_bytes()
            ansible([plays[0]], expect_success=False)
            assert command(["docker", "inspect", first, "--format", "{{.State.Running}}"] ) == "true"
            assert (project / ".env").read_bytes() == env_before
            assert {p.name: p.read_bytes() for p in credentials.iterdir()} == original_credentials

            native_code = """import os,subprocess
from pathlib import Path
from app.core.native_contexts import _contexts
from app.core.native_scenarios import inspect_native_scenario
from app.core.native_execution import prepare_native_run
from app.core.ssh_agent import _start_agent
context=_contexts()[0];root=Path('/home/range42/native-smoke')
run=prepare_native_run(root,inspect_native_scenario(root,'scenarios/smoke'),context,
 scope='full',features={},parameters={},artifact_dir=Path('/home/range42/native-acceptance'))
agent=_start_agent(context.workspace)
try:
 result=subprocess.run(run.command,env={**os.environ,**agent.env},capture_output=True,text=True)
 assert result.returncode==0,result.stdout+result.stderr
 assert 'Read-only file system' not in result.stderr,result.stderr
 assert 'native-localhost-only' in result.stdout,result.stdout
 assert not Path('/runtime/range42-ansible_roles-debug-devkit/secrets').exists()
 print('Actual native context and local Ansible scenario passed')
finally:agent.close()"""
            assert "passed" in command(compose + ["exec", "-T", "api", "python", "-c", native_code])
            command(["docker", "stop", first])
            ansible([plays[0], packaging, plays[5]])
            second = command(compose + ["ps", "-q", "api"])
            assert client.get("/v1/health/ready", headers=headers).json()["ready"] is True
            assert client.get("/v1/proxmox/hosts", headers=headers).json()["items"][0]["id"] == host_id
            assert {p.name: p.read_bytes() for p in credentials.iterdir()} == original_credentials
            command(["docker", "stop", second])
            token_file = credentials / "api-token"
            saved = token_file.read_bytes()
            token_file.unlink()
            ansible([plays[0]], expect_success=False)
            assert not command(compose + ["ps", "-q", "api"])
            private_file(token_file, saved)
    finally:
        subprocess.run(compose + ["down", "-v", "--remove-orphans"], env=env, capture_output=True, timeout=60)
        subprocess.run(["docker", "rm", "-f", fake, scratch], env=env, capture_output=True, timeout=30)
        subprocess.run(["docker", "image", "rm", image], env=env, capture_output=True, timeout=30)
